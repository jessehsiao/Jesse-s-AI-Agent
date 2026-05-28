"""Configuration loading for strands-bedrock-agent.

Resolves configuration with precedence: CLI > env > file > default.
Pure resolution logic — no I/O against AWS or MCP services.

Requirements: 3.2, 3.3, 4.2, 4.4, 4.5, 7.2, 7.3, 9.2, 9.3
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from strands_bedrock_agent.errors import ConfigError

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL_ID: str = "global.anthropic.claude-opus-4-5-20251101-v1:0"
DEFAULT_LOG_LEVEL: str = "INFO"
DEFAULT_MCP_CONFIG_PATH: Path = Path(".kiro/settings/mcp.json")
DEFAULT_SKILLS_DIR: Path = Path("skills")
DEFAULT_WEB_PORT: int = 8765
DEFAULT_WEB_HOST: str = "127.0.0.1"
DEFAULT_MAX_PROMPT_LENGTH: int = 10000
DEFAULT_MCP_CONNECT_TIMEOUT: int = 10
DEFAULT_MCP_TOOL_TIMEOUT: int = 30
DEFAULT_WEB_REQUEST_TIMEOUT: int = 120

VALID_LOG_LEVELS: set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
AWS_REGION_RE: str = r"^[a-z]{2}-[a-z]+-\d+$"


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Immutable application configuration resolved from multiple sources."""

    bedrock_model_id: str
    aws_region: str
    aws_profile: Optional[str]
    log_level: str
    mcp_config_path: Path
    mcp_connect_timeout: int
    mcp_tool_timeout: int
    web_port: int
    web_host: str
    allow_non_loopback: bool
    web_request_timeout: int
    max_prompt_length: int
    skills_dir: Path
    # Diagnostic: which sources contributed (for error messages, R3.5)
    region_sources_checked: tuple[str, ...]
    log_level_was_invalid: bool  # if True, logging_setup must emit a WARNING (R7.3)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _positive_int(value: str, fallback: int) -> int:
    """Parse a string as a positive integer, returning fallback on failure."""
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (ValueError, TypeError):
        return fallback


def _load_file_config(file_path: Optional[Path]) -> dict:
    """Load configuration from a JSON file if it exists.

    Returns an empty dict if file_path is None or the file does not exist.
    """
    if file_path is None:
        return {}
    path = Path(file_path)
    if not path.is_file():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _resolve_boto3_profile_region(profile: Optional[str]) -> Optional[str]:
    """Look up the region configured in the AWS profile via botocore.

    This avoids importing full boto3 just for config resolution.
    Never reads or returns AWS credentials (R4.5).
    """
    try:
        import botocore.session

        session = botocore.session.Session(profile=profile)
        return session.get_config_variable("region")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def load_config(
    *,
    cli_overrides: Optional[dict] = None,
    env: Optional[dict] = None,
    file_path: Optional[Path] = None,
) -> Config:
    """Resolve configuration with precedence: CLI > env > file > default.

    Args:
        cli_overrides: Values from CLI argument parsing (highest precedence).
        env: Environment variable mapping. Defaults to os.environ.
        file_path: Optional path to a JSON config file.

    Returns:
        A frozen Config dataclass with all resolved values.

    Raises:
        ConfigError: if required values are unresolvable (e.g., region missing).
    """
    cli = cli_overrides or {}
    environ = env if env is not None else os.environ
    file_cfg = _load_file_config(file_path)

    # --- AWS profile (needed for boto3 region lookup) ---
    aws_profile: Optional[str] = (
        cli.get("aws_profile")
        or environ.get("AWS_PROFILE")
        or file_cfg.get("aws_profile")
        or None
    )

    # --- Bedrock model ID ---
    bedrock_model_id: str = (
        cli.get("bedrock_model_id")
        or environ.get("BEDROCK_MODEL_ID")
        or file_cfg.get("bedrock_model_id")
        or DEFAULT_MODEL_ID
    )

    # --- Log level (invalid does NOT raise; sets flag) ---
    raw_log_level: Optional[str] = (
        cli.get("log_level")
        or environ.get("LOG_LEVEL")
        or file_cfg.get("log_level")
    )
    log_level_was_invalid = False
    if raw_log_level is not None:
        normalized = raw_log_level.strip().upper()
        if normalized in VALID_LOG_LEVELS:
            log_level = normalized
        else:
            log_level = DEFAULT_LOG_LEVEL
            log_level_was_invalid = True
    else:
        log_level = DEFAULT_LOG_LEVEL

    # --- MCP config path ---
    raw_mcp_path = (
        cli.get("mcp_config_path")
        or environ.get("MCP_CONFIG_PATH")
        or file_cfg.get("mcp_config_path")
    )
    mcp_config_path = Path(raw_mcp_path) if raw_mcp_path else DEFAULT_MCP_CONFIG_PATH

    # --- MCP connect timeout ---
    raw_mcp_connect = (
        cli.get("mcp_connect_timeout")
        or environ.get("MCP_CONNECT_TIMEOUT_SECONDS")
        or file_cfg.get("mcp_connect_timeout")
    )
    mcp_connect_timeout = (
        _positive_int(str(raw_mcp_connect), DEFAULT_MCP_CONNECT_TIMEOUT)
        if raw_mcp_connect is not None
        else DEFAULT_MCP_CONNECT_TIMEOUT
    )

    # --- MCP tool timeout ---
    raw_mcp_tool = (
        cli.get("mcp_tool_timeout")
        or environ.get("MCP_TOOL_TIMEOUT_SECONDS")
        or file_cfg.get("mcp_tool_timeout")
    )
    mcp_tool_timeout = (
        _positive_int(str(raw_mcp_tool), DEFAULT_MCP_TOOL_TIMEOUT)
        if raw_mcp_tool is not None
        else DEFAULT_MCP_TOOL_TIMEOUT
    )

    # --- Web port ---
    raw_port = (
        cli.get("port")
        or environ.get("WEB_PORT")
        or file_cfg.get("web_port")
    )
    if raw_port is not None:
        try:
            web_port = int(raw_port)
            if not (1024 <= web_port <= 65535):
                web_port = DEFAULT_WEB_PORT
        except (ValueError, TypeError):
            web_port = DEFAULT_WEB_PORT
    else:
        web_port = DEFAULT_WEB_PORT

    # --- Web host ---
    web_host: str = (
        cli.get("host")
        or environ.get("WEB_HOST")
        or file_cfg.get("web_host")
        or DEFAULT_WEB_HOST
    )

    # --- Allow non-loopback ---
    allow_non_loopback: bool = bool(cli.get("allow_non_loopback", False))

    # --- Web request timeout ---
    raw_web_timeout = (
        cli.get("web_request_timeout")
        or environ.get("WEB_REQUEST_TIMEOUT_SECONDS")
        or file_cfg.get("web_request_timeout")
    )
    web_request_timeout = (
        _positive_int(str(raw_web_timeout), DEFAULT_WEB_REQUEST_TIMEOUT)
        if raw_web_timeout is not None
        else DEFAULT_WEB_REQUEST_TIMEOUT
    )

    # --- Max prompt length ---
    raw_max_prompt = (
        cli.get("max_prompt_length")
        or environ.get("MAX_PROMPT_LENGTH")
        or file_cfg.get("max_prompt_length")
    )
    max_prompt_length = (
        _positive_int(str(raw_max_prompt), DEFAULT_MAX_PROMPT_LENGTH)
        if raw_max_prompt is not None
        else DEFAULT_MAX_PROMPT_LENGTH
    )

    # --- Skills directory ---
    raw_skills_dir = (
        cli.get("skills_dir")
        or environ.get("SKILLS_DIR")
        or file_cfg.get("skills_dir")
    )
    skills_dir = Path(raw_skills_dir) if raw_skills_dir else DEFAULT_SKILLS_DIR

    # --- AWS region (multi-source resolution with tracking) ---
    region_sources_checked: list[str] = []
    aws_region: Optional[str] = None

    # Source 1: CLI override
    cli_region = cli.get("region")
    region_sources_checked.append("cli_overrides['region']")
    if cli_region and re.match(AWS_REGION_RE, cli_region):
        aws_region = cli_region

    # Source 2: env AWS_REGION
    if aws_region is None:
        env_region = environ.get("AWS_REGION")
        region_sources_checked.append("env['AWS_REGION']")
        if env_region and re.match(AWS_REGION_RE, env_region):
            aws_region = env_region

    # Source 3: env AWS_DEFAULT_REGION
    if aws_region is None:
        env_default_region = environ.get("AWS_DEFAULT_REGION")
        region_sources_checked.append("env['AWS_DEFAULT_REGION']")
        if env_default_region and re.match(AWS_REGION_RE, env_default_region):
            aws_region = env_default_region

    # Source 4: boto3 profile region
    if aws_region is None:
        region_sources_checked.append("boto3_profile_region")
        boto3_region = _resolve_boto3_profile_region(aws_profile)
        if boto3_region and re.match(AWS_REGION_RE, boto3_region):
            aws_region = boto3_region

    # If still unresolved, raise ConfigError listing all sources checked
    if aws_region is None:
        raise ConfigError("aws_region", checked=tuple(region_sources_checked))

    return Config(
        bedrock_model_id=bedrock_model_id,
        aws_region=aws_region,
        aws_profile=aws_profile,
        log_level=log_level,
        mcp_config_path=mcp_config_path,
        mcp_connect_timeout=mcp_connect_timeout,
        mcp_tool_timeout=mcp_tool_timeout,
        web_port=web_port,
        web_host=web_host,
        allow_non_loopback=allow_non_loopback,
        web_request_timeout=web_request_timeout,
        max_prompt_length=max_prompt_length,
        skills_dir=skills_dir,
        region_sources_checked=tuple(region_sources_checked),
        log_level_was_invalid=log_level_was_invalid,
    )
