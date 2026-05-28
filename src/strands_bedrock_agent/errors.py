"""Error taxonomy for strands-bedrock-agent.

Defines structured error classes, CLI exit code mapping, and a sanitised
error rendering function that strips credentials and stack traces from
operator-visible messages.

Requirements: 3.5, 3.6, 3.7, 4.6, 4.7, 4.8, 5.6, 5.7, 7.7, 7.8, 9.11
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# CLI exit codes (design table)
# ---------------------------------------------------------------------------

EXIT_OK: int = 0
EXIT_USAGE: int = 2
EXIT_CONFIG: int = 3
EXIT_CREDENTIALS: int = 4
EXIT_MODEL_UNAVAILABLE: int = 5
EXIT_AGENT_ERROR: int = 6
EXIT_BEDROCK_RETRY_EXHAUSTED: int = 7


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Missing or invalid required configuration value (R3.5, R4.3)."""

    def __init__(self, knob: str, *, checked: tuple[str, ...] = ()) -> None:
        self.knob = knob
        self.checked = checked
        sources = ", ".join(checked) if checked else "none"
        super().__init__(
            f"Required configuration '{knob}' is missing. "
            f"Sources checked: {sources}"
        )


class CredentialsError(Exception):
    """AWS credentials cannot be resolved (R4.6, R4.8)."""

    def __init__(self, message: str, *, profile: Optional[str] = None) -> None:
        self.profile = profile
        super().__init__(message)


class ModelUnavailableError(Exception):
    """Configured Bedrock model not available in the target region (R3.6)."""

    def __init__(self, model_id: str, region: str, *, hint: str = "") -> None:
        self.model_id = model_id
        self.region = region
        self.hint = hint
        msg = f"Model '{model_id}' is not available in region '{region}'."
        if hint:
            msg += f" Hint: {hint}"
        super().__init__(msg)


class BedrockAccessDeniedError(Exception):
    """IAM denies bedrock:InvokeModel (R3.7, R4.7)."""

    def __init__(
        self, model_id: str, region: str, *, aws_error_code: str = ""
    ) -> None:
        self.model_id = model_id
        self.region = region
        self.aws_error_code = aws_error_code
        msg = f"Access denied for model '{model_id}' in region '{region}'."
        if aws_error_code:
            msg += f" AWS error code: {aws_error_code}"
        super().__init__(msg)


class BedrockRetryExhaustedError(Exception):
    """All Bedrock retries exhausted (R7.7)."""

    def __init__(
        self, model_id: str, *, aws_error_code: str = "", attempts: int = 0
    ) -> None:
        self.model_id = model_id
        self.aws_error_code = aws_error_code
        self.attempts = attempts
        msg = (
            f"Bedrock retries exhausted for model '{model_id}' "
            f"after {attempts} attempts."
        )
        if aws_error_code:
            msg += f" Last AWS error code: {aws_error_code}"
        super().__init__(msg)


class MCPToolError(Exception):
    """Server-side error during an MCP tool call (R5.6, R7.8)."""

    def __init__(
        self, server_name: str, tool_name: str, *, error_description: str = ""
    ) -> None:
        self.server_name = server_name
        self.tool_name = tool_name
        self.error_description = error_description
        msg = f"MCP tool error: server='{server_name}', tool='{tool_name}'."
        if error_description:
            msg += f" Detail: {error_description}"
        super().__init__(msg)


class MCPToolTimeoutError(Exception):
    """MCP tool call did not respond within the configured timeout (R5.7)."""

    def __init__(
        self, server_name: str, tool_name: str, *, timeout_seconds: int = 0
    ) -> None:
        self.server_name = server_name
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds
        msg = (
            f"MCP tool timeout: server='{server_name}', tool='{tool_name}' "
            f"did not respond within {timeout_seconds}s."
        )
        super().__init__(msg)


class ToolRegistrationError(Exception):
    """Expected tool absent from registry post-build (R2.6)."""

    def __init__(self, *, missing: list[str]) -> None:
        self.missing = missing
        names = ", ".join(missing)
        super().__init__(f"Tool registration failed. Missing tools: {names}")


class StrandsCompatError(Exception):
    """Strands SDK class/method missing or signature mismatch (R2.7)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class PromptValidationError(Exception):
    """Prompt is empty, whitespace-only, or exceeds max length (R2.4, R6.3, R9.8)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class PortValidationError(Exception):
    """--port value is not an integer or is outside the accepted range (R9.4)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class PortInUseError(Exception):
    """Requested port is already in use (R9.4)."""

    def __init__(self, port: int, *, host: str = "127.0.0.1") -> None:
        self.port = port
        self.host = host
        super().__init__(f"Port {port} is already in use on {host}.")


class AgentError(Exception):
    """Catch-all for unhandled exceptions inside the Agent (R6.7, R6.8, R9.11)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# Category -> exit code mapping
# ---------------------------------------------------------------------------

CATEGORY_EXIT_CODES: dict[str, int] = {
    "config": EXIT_CONFIG,
    "credentials": EXIT_CREDENTIALS,
    "model_unavailable": EXIT_MODEL_UNAVAILABLE,
    "agent": EXIT_AGENT_ERROR,
    "bedrock_retry_exhausted": EXIT_BEDROCK_RETRY_EXHAUSTED,
    "usage": EXIT_USAGE,
    "mcp": EXIT_AGENT_ERROR,
    "strands_compat": EXIT_AGENT_ERROR,
    "port": EXIT_USAGE,
    "unhandled": EXIT_AGENT_ERROR,
}

# Mapping from exception class to category string
ERROR_CLASS_CATEGORY: dict[type, str] = {
    ConfigError: "config",
    CredentialsError: "credentials",
    ModelUnavailableError: "model_unavailable",
    BedrockAccessDeniedError: "agent",
    BedrockRetryExhaustedError: "bedrock_retry_exhausted",
    MCPToolError: "mcp",
    MCPToolTimeoutError: "mcp",
    ToolRegistrationError: "agent",
    StrandsCompatError: "strands_compat",
    PromptValidationError: "usage",
    PortValidationError: "port",
    PortInUseError: "port",
    AgentError: "agent",
}


# ---------------------------------------------------------------------------
# Sanitised error rendering (Property 10)
# ---------------------------------------------------------------------------

# Regex matching AWS access key IDs (AKIA... or ASIA... followed by 16 uppercase
# alphanumeric characters).
_AWS_KEY_RE = re.compile(r"(AKIA|ASIA)[0-9A-Z]{16}")

# Pattern matching Python traceback header lines.
_TRACEBACK_RE = re.compile(r"Traceback\s*(\(most recent call last\):?)?")


def render_error(category: str, message: str) -> str:
    """Return a single human-readable error line with sensitive data stripped.

    Strips:
      - AWS access-key-shaped substrings matching (AKIA|ASIA)[0-9A-Z]{16}
      - Traceback headers (e.g. "Traceback (most recent call last):")

    Returns:
      A string in the format "[category] message".
    """
    sanitised = _AWS_KEY_RE.sub("", message)
    sanitised = _TRACEBACK_RE.sub("", sanitised)
    # Collapse any resulting double-spaces from removals
    sanitised = " ".join(sanitised.split())
    return f"[{category}] {sanitised}"
