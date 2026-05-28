"""Example-based unit tests for config.py.

Covers:
- Invalid LOG_LEVEL returns INFO with log_level_was_invalid=True
- Explicit aws_profile is preserved in the Config
- MCP_CONFIG_PATH env override resolves to the supplied path
- Web port default is 8765
- Max prompt length default is 10000

Requirements: 7.3, 4.4, 5.1, 9.2, 2.4, 6.3
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from strands_bedrock_agent.config import (
    Config,
    DEFAULT_MAX_PROMPT_LENGTH,
    DEFAULT_MCP_CONFIG_PATH,
    DEFAULT_WEB_PORT,
    load_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_env(**overrides: str) -> dict[str, str]:
    """Return a minimal env dict with a valid region, merged with overrides."""
    env = {"AWS_REGION": "us-east-1"}
    env.update(overrides)
    return env


def _load_with_env(**env_overrides: str) -> Config:
    """Load config with a patched boto3 region lookup and the given env vars."""
    with patch(
        "strands_bedrock_agent.config._resolve_boto3_profile_region",
        return_value=None,
    ):
        return load_config(env=_base_env(**env_overrides))


def _load_with_cli_and_env(cli: dict, **env_overrides: str) -> Config:
    """Load config with CLI overrides, patched boto3, and given env vars."""
    with patch(
        "strands_bedrock_agent.config._resolve_boto3_profile_region",
        return_value=None,
    ):
        return load_config(cli_overrides=cli, env=_base_env(**env_overrides))


# ---------------------------------------------------------------------------
# Tests: Invalid LOG_LEVEL returns INFO with log_level_was_invalid=True (R7.3)
# ---------------------------------------------------------------------------


class TestInvalidLogLevel:
    """Requirement 7.3: invalid LOG_LEVEL falls back to INFO with a flag."""

    def test_nonsense_log_level_returns_info(self):
        cfg = _load_with_env(LOG_LEVEL="BANANA")
        assert cfg.log_level == "INFO"
        assert cfg.log_level_was_invalid is True

    def test_numeric_log_level_returns_info(self):
        cfg = _load_with_env(LOG_LEVEL="42")
        assert cfg.log_level == "INFO"
        assert cfg.log_level_was_invalid is True

    def test_empty_string_log_level_uses_default(self):
        """Empty string is falsy so treated as absent — default INFO, no flag."""
        cfg = _load_with_env(LOG_LEVEL="")
        assert cfg.log_level == "INFO"
        assert cfg.log_level_was_invalid is False

    def test_valid_log_level_debug_is_accepted(self):
        cfg = _load_with_env(LOG_LEVEL="debug")
        assert cfg.log_level == "DEBUG"
        assert cfg.log_level_was_invalid is False

    def test_valid_log_level_warning_mixed_case(self):
        cfg = _load_with_env(LOG_LEVEL="WaRnInG")
        assert cfg.log_level == "WARNING"
        assert cfg.log_level_was_invalid is False


# ---------------------------------------------------------------------------
# Tests: Explicit aws_profile is preserved (R4.4)
# ---------------------------------------------------------------------------


class TestAwsProfilePreserved:
    """Requirement 4.4: explicit aws_profile is preserved in Config."""

    def test_profile_from_env(self):
        cfg = _load_with_env(AWS_PROFILE="my-dev-profile")
        assert cfg.aws_profile == "my-dev-profile"

    def test_profile_from_cli_overrides(self):
        cfg = _load_with_cli_and_env({"aws_profile": "cli-profile"})
        assert cfg.aws_profile == "cli-profile"

    def test_no_profile_defaults_to_none(self):
        cfg = _load_with_env()
        assert cfg.aws_profile is None


# ---------------------------------------------------------------------------
# Tests: MCP_CONFIG_PATH env override resolves to the supplied path (R5.1)
# ---------------------------------------------------------------------------


class TestMcpConfigPathOverride:
    """Requirement 5.1: MCP_CONFIG_PATH env var overrides the default path."""

    def test_env_override_resolves_to_supplied_path(self):
        cfg = _load_with_env(MCP_CONFIG_PATH="/custom/path/mcp.json")
        assert cfg.mcp_config_path == Path("/custom/path/mcp.json")

    def test_relative_path_is_preserved(self):
        cfg = _load_with_env(MCP_CONFIG_PATH="relative/mcp.json")
        assert cfg.mcp_config_path == Path("relative/mcp.json")

    def test_default_mcp_config_path_when_unset(self):
        cfg = _load_with_env()
        assert cfg.mcp_config_path == DEFAULT_MCP_CONFIG_PATH


# ---------------------------------------------------------------------------
# Tests: Web port default is 8765 (R9.2)
# ---------------------------------------------------------------------------


class TestWebPortDefault:
    """Requirement 9.2: web port defaults to 8765."""

    def test_default_web_port(self):
        cfg = _load_with_env()
        assert cfg.web_port == 8765
        assert cfg.web_port == DEFAULT_WEB_PORT

    def test_web_port_from_env(self):
        cfg = _load_with_env(WEB_PORT="9000")
        assert cfg.web_port == 9000

    def test_invalid_web_port_falls_back_to_default(self):
        cfg = _load_with_env(WEB_PORT="not-a-number")
        assert cfg.web_port == DEFAULT_WEB_PORT


# ---------------------------------------------------------------------------
# Tests: Max prompt length default is 10000 (R2.4, R6.3)
# ---------------------------------------------------------------------------


class TestMaxPromptLengthDefault:
    """Requirements 2.4, 6.3: max prompt length defaults to 10000."""

    def test_default_max_prompt_length(self):
        cfg = _load_with_env()
        assert cfg.max_prompt_length == 10000
        assert cfg.max_prompt_length == DEFAULT_MAX_PROMPT_LENGTH

    def test_max_prompt_length_from_env(self):
        cfg = _load_with_env(MAX_PROMPT_LENGTH="5000")
        assert cfg.max_prompt_length == 5000

    def test_invalid_max_prompt_length_falls_back_to_default(self):
        cfg = _load_with_env(MAX_PROMPT_LENGTH="abc")
        assert cfg.max_prompt_length == DEFAULT_MAX_PROMPT_LENGTH
