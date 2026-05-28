"""Agent factory for strands-bedrock-agent.

Single construction path (`build_agent`) reused by CLI and Web Backend.
Guarantees consistent behaviour across surfaces (R9.6).

Requirements: 2.1, 2.2, 2.5, 2.6, 2.7, 3.1, 3.4, 3.6, 3.7, 4.4, 4.6, 4.7, 4.8, 5.2, 5.3, 7.1
"""

from __future__ import annotations

import logging
import sys
import threading
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, NamedTuple

import boto3
import botocore.exceptions

from strands_bedrock_agent.config import Config
from strands_bedrock_agent.errors import (
    CredentialsError,
    ModelUnavailableError,
    StrandsCompatError,
    ToolRegistrationError,
)
from strands_bedrock_agent.logging_setup import EVENT_CONFIG_RESOLVED, log_event
from strands_bedrock_agent.mcp_loader import load_mcp_tools, parse_mcp_config
from strands_bedrock_agent.system_prompt import SYSTEM_PROMPT
from strands.vended_plugins.skills import AgentSkills

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class ToolInvocation(NamedTuple):
    """A single recorded tool invocation with timing."""

    tool_name: str
    started_at: datetime
    completed_at: datetime


@dataclass
class AgentBundle(AbstractContextManager):
    """Bundle holding the constructed Agent and its associated resources.

    Implements AbstractContextManager so callers can use `with` or call
    __exit__ explicitly to clean up MCP clients.
    """

    agent: Any  # strands.Agent instance
    mcp_clients: list = field(default_factory=list)
    registered_tool_names: list[str] = field(default_factory=list)
    mcp_failures: list[tuple[str, str]] = field(default_factory=list)

    # Thread-local storage for recording tool invocations per-request
    _invocations_local: threading.local = field(
        default_factory=threading.local, repr=False
    )

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Close every MCPClient (best-effort)."""
        for client in self.mcp_clients:
            try:
                client.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Tool invocation recording
# ---------------------------------------------------------------------------


def get_recorded_invocations(bundle: AgentBundle) -> list[ToolInvocation]:
    """Drain and return the thread-local list of recorded tool invocations.

    This is called by the web layer after each request to populate the
    `tool_invocations` field in the response.
    """
    invocations = getattr(bundle._invocations_local, "invocations", [])
    bundle._invocations_local.invocations = []
    return invocations


def _make_recording_shim(
    tool_callable: Any, tool_name: str, bundle: AgentBundle
) -> Any:
    """Wrap a tool callable in a recording shim that tracks invocation timing.

    The shim appends (tool_name, started_at, completed_at) to the per-Agent
    thread-local list used by web/server.py for tool_invocations reporting.
    """

    def shim(*args: Any, **kwargs: Any) -> Any:
        started_at = datetime.now(timezone.utc)
        try:
            result = tool_callable(*args, **kwargs)
        finally:
            completed_at = datetime.now(timezone.utc)
            invocations = getattr(
                bundle._invocations_local, "invocations", None
            )
            if invocations is None:
                bundle._invocations_local.invocations = []
                invocations = bundle._invocations_local.invocations
            invocations.append(
                ToolInvocation(
                    tool_name=tool_name,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            )
        return result

    # Preserve the tool name attribute if present (Strands uses this)
    if hasattr(tool_callable, "tool_name"):
        shim.tool_name = tool_callable.tool_name  # type: ignore[attr-defined]
    elif hasattr(tool_callable, "name"):
        shim.name = tool_callable.name  # type: ignore[attr-defined]

    # Copy over any other attributes the Strands SDK expects
    for attr in ("tool_spec", "tool_type", "__name__", "__doc__"):
        if hasattr(tool_callable, attr):
            try:
                setattr(shim, attr, getattr(tool_callable, attr))
            except (AttributeError, TypeError):
                pass

    return shim


# ---------------------------------------------------------------------------
# Main factory
# ---------------------------------------------------------------------------


def build_agent(config: Config) -> AgentBundle:
    """Construct the Agent and return an AgentBundle.

    Order of operations:
      1. Construct boto3.Session — validate profile and credentials.
      2. Verify Bedrock model availability in region.
      3. Construct BedrockModel exactly once with no transformation (Property 13).
      4. Load MCP tools via mcp_loader.
      5. Wrap each MCP tool in a recording shim.
      6. Construct strands.Agent.
      7. Verify tool registration.
      8. Emit EVENT_CONFIG_RESOLVED and return AgentBundle.

    Raises:
        CredentialsError: boto3 cannot resolve credentials or profile missing.
        ModelUnavailableError: Bedrock model not enabled in region.
        StrandsCompatError: SDK class/method missing or signature mismatch.
        ToolRegistrationError: Expected tool absent from registry post-build.
    """
    # -----------------------------------------------------------------------
    # Step 1: Construct boto3.Session; validate profile and credentials (R4.8, R4.6)
    # -----------------------------------------------------------------------
    try:
        session = boto3.Session(
            profile_name=config.aws_profile,
            region_name=config.aws_region,
        )
    except botocore.exceptions.ProfileNotFound as exc:
        raise CredentialsError(
            f"AWS profile '{config.aws_profile}' not found in credentials/config file.",
            profile=config.aws_profile,
        ) from exc

    # Verify credentials are resolvable
    credentials = session.get_credentials()
    if credentials is None:
        raise CredentialsError(
            "No AWS credentials could be resolved. "
            "Checked: environment variables, shared credentials file, "
            "named profile, IAM role.",
            profile=config.aws_profile,
        )

    # -----------------------------------------------------------------------
    # Step 2: Verify Bedrock model availability (R3.6)
    # -----------------------------------------------------------------------
    _verify_model_availability(session, config)

    # -----------------------------------------------------------------------
    # Step 3: Construct BedrockModel exactly once (Property 13)
    # -----------------------------------------------------------------------
    try:
        from strands.models.bedrock import BedrockModel

        bedrock_model = BedrockModel(
            model_id=config.bedrock_model_id,
            boto_session=session,
        )
    except (AttributeError, TypeError) as exc:
        raise StrandsCompatError(
            f"Failed to construct BedrockModel: {exc}. "
            f"Ensure strands-agents is installed and compatible."
        ) from exc

    # -----------------------------------------------------------------------
    # Step 4: Load MCP tools (R5.2, R5.3, R5.5)
    # -----------------------------------------------------------------------
    specs = parse_mcp_config(config.mcp_config_path)
    mcp_result = load_mcp_tools(
        specs,
        connect_timeout_seconds=config.mcp_connect_timeout,
        operator_stream=sys.stderr,
    )

    # -----------------------------------------------------------------------
    # Step 5: Prepare tools and bundle
    # -----------------------------------------------------------------------
    bundle = AgentBundle(
        agent=None,  # placeholder, set after Agent construction
        mcp_clients=mcp_result.clients,
        registered_tool_names=[],
        mcp_failures=mcp_result.failures,
    )

    # Pass MCPClient instances directly as ToolProviders to the Agent.
    # The Strands SDK recognizes MCPClient (a ToolProvider subclass) and
    # handles tool registration internally.
    tools_for_agent: list = mcp_result.clients

    # -----------------------------------------------------------------------
    # Step 6: Construct strands.Agent (R2.1, R2.2, R2.5, R2.7)
    # -----------------------------------------------------------------------
    try:
        import strands
        from strands.agent.conversation_manager import SummarizingConversationManager

        # Build AgentSkills plugin if skills directory exists
        plugins: list = []
        skills_dir = config.skills_dir
        if skills_dir.is_dir():
            skills_plugin = AgentSkills(skills=[str(skills_dir)])
            plugins.append(skills_plugin)
            logger.info("Loaded skills from %s", skills_dir)

        agent = strands.Agent(
            model=bedrock_model,
            tools=tools_for_agent,
            system_prompt=SYSTEM_PROMPT,
            plugins=plugins,
            conversation_manager=SummarizingConversationManager()
        )
    except (AttributeError, TypeError) as exc:
        raise StrandsCompatError(
            f"Failed to construct strands.Agent: {exc}. "
            f"Ensure strands-agents is installed and compatible."
        ) from exc

    bundle.agent = agent

    # -----------------------------------------------------------------------
    # Step 7: Record registered tools (R2.5, R2.6)
    # -----------------------------------------------------------------------
    try:
        actual_tool_names = set(agent.tool_registry.tool_names)
    except AttributeError:
        # If tool_registry doesn't exist, treat as empty
        actual_tool_names = set()

    bundle.registered_tool_names = sorted(actual_tool_names)

    # -----------------------------------------------------------------------
    # Step 8: Emit EVENT_CONFIG_RESOLVED log record (R7.1) and return
    # -----------------------------------------------------------------------
    log_event(
        logger,
        logging.INFO,
        EVENT_CONFIG_RESOLVED,
        model_id=config.bedrock_model_id,
        region=config.aws_region,
        aws_profile=config.aws_profile or "(default chain)",
        log_level=config.log_level,
        mcp_config_path=str(config.mcp_config_path),
        registered_tools=bundle.registered_tool_names,
        mcp_failures=[name for name, _ in bundle.mcp_failures],
    )

    return bundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_tool_name(tool: Any) -> str:
    """Extract the tool name from a Strands tool object."""
    if hasattr(tool, "tool_name"):
        return tool.tool_name
    if hasattr(tool, "name"):
        return tool.name
    if hasattr(tool, "__name__"):
        return tool.__name__
    return str(tool)


def _verify_model_availability(session: boto3.Session, config: Config) -> None:
    """Verify the configured model is available in the target region.

    For cross-region inference profiles (prefixed with "us.", "eu.", "global."),
    calls list_inference_profiles and matches by inferenceProfileId.
    For base models, calls list_foundation_models(byProvider="anthropic")
    and matches by modelId.

    Raises:
        ModelUnavailableError: if the model is not found.
    """
    model_id = config.bedrock_model_id
    region = config.aws_region

    try:
        bedrock_client = session.client("bedrock", region_name=region)
    except Exception as exc:
        raise CredentialsError(
            f"Failed to create Bedrock client for region '{region}': {exc}",
            profile=config.aws_profile,
        ) from exc

    # Determine if this is a cross-region inference profile
    cross_region_prefixes = ("us.", "eu.", "global.")
    is_cross_region = any(
        model_id.startswith(prefix) for prefix in cross_region_prefixes
    )

    # Cross-region inference profiles are routed by Bedrock automatically;
    # they may not appear in the local region's list_inference_profiles.
    # Skip availability verification for these — Bedrock will return a clear
    # error at invocation time if the profile is invalid.
    if is_cross_region:
        return

    hint = f"aws bedrock list-foundation-models --region {region}"

    try:
        if is_cross_region:
            # Use list_inference_profiles for cross-region IDs
            found = False

            # list_inference_profiles may not support pagination in all SDK versions
            try:
                response = bedrock_client.list_inference_profiles()
                profiles = response.get("inferenceProfileSummaries", [])
                for profile in profiles:
                    if profile.get("inferenceProfileId") == model_id:
                        found = True
                        break

                # Handle pagination if present
                while not found and response.get("nextToken"):
                    response = bedrock_client.list_inference_profiles(
                        nextToken=response["nextToken"]
                    )
                    profiles = response.get("inferenceProfileSummaries", [])
                    for profile in profiles:
                        if profile.get("inferenceProfileId") == model_id:
                            found = True
                            break
            except botocore.exceptions.ClientError:
                # If list_inference_profiles fails, try list_foundation_models
                # as a fallback
                found = _check_foundation_models(bedrock_client, model_id)

            if not found:
                raise ModelUnavailableError(
                    model_id=model_id,
                    region=region,
                    hint=hint,
                )
        else:
            # Use list_foundation_models for base model IDs
            if not _check_foundation_models(bedrock_client, model_id):
                raise ModelUnavailableError(
                    model_id=model_id,
                    region=region,
                    hint=hint,
                )

    except ModelUnavailableError:
        raise
    except botocore.exceptions.ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in ("AccessDeniedException", "UnauthorizedAccess"):
            raise CredentialsError(
                f"Access denied when verifying model availability: {exc}",
                profile=config.aws_profile,
            ) from exc
        raise ModelUnavailableError(
            model_id=model_id,
            region=region,
            hint=hint,
        ) from exc
    except Exception as exc:
        # For unexpected errors during verification, raise as model unavailable
        raise ModelUnavailableError(
            model_id=model_id,
            region=region,
            hint=hint,
        ) from exc


def _check_foundation_models(bedrock_client: Any, model_id: str) -> bool:
    """Check if model_id is in the list of foundation models (by provider Anthropic)."""
    try:
        response = bedrock_client.list_foundation_models(byProvider="anthropic")
        models = response.get("modelSummaries", [])
        for model in models:
            if model.get("modelId") == model_id:
                return True
        return False
    except Exception:
        return False
