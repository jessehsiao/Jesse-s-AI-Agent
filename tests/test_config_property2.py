"""Property-based tests for configuration precedence (Property 2).

Feature: strands-bedrock-agent, Property 2: Configuration precedence is monotone

Validates: Requirements 3.2, 3.3, 4.2
"""

from __future__ import annotations

import tempfile
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis.strategies import text, none, one_of

from strands_bedrock_agent.config import load_config, DEFAULT_MODEL_ID
from strands_bedrock_agent.errors import ConfigError


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate either a non-empty string (1-256 chars) or None
_value_strategy = one_of(
    none(),
    text(min_size=1, max_size=256),
)


# ---------------------------------------------------------------------------
# Property 2: Configuration precedence is monotone
# ---------------------------------------------------------------------------


class TestConfigPrecedenceMonotone:
    """Feature: strands-bedrock-agent, Property 2: Configuration precedence is monotone"""

    @given(
        env_value=_value_strategy,
        file_value=_value_strategy,
    )
    @settings(max_examples=100)
    def test_bedrock_model_id_precedence_env_over_file(
        self, env_value: str | None, file_value: str | None
    ):
        """Feature: strands-bedrock-agent, Property 2: Configuration precedence is monotone

        For bedrock_model_id: env > file > default. The resolved value is the
        highest-priority non-None component.

        Validates: Requirements 3.2, 3.3, 4.2
        """
        # We need a valid region to avoid ConfigError on region resolution
        env = {"AWS_REGION": "us-east-1"}
        if env_value is not None:
            env["BEDROCK_MODEL_ID"] = env_value

        # Write file config if file_value is provided
        file_path = None
        if file_value is not None:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            json.dump({"bedrock_model_id": file_value}, tmp)
            tmp.close()
            file_path = Path(tmp.name)

        # Patch boto3 region lookup to avoid real AWS calls
        with patch(
            "strands_bedrock_agent.config._resolve_boto3_profile_region",
            return_value=None,
        ):
            config = load_config(env=env, file_path=file_path)

        # Determine expected value based on precedence: env > file > default
        # Note: Python's `or` short-circuits on falsy values (empty string is falsy),
        # but the config module uses `or` chaining which treats empty string as falsy.
        # The actual precedence in load_config uses `or` which skips empty strings.
        if env_value:
            expected = env_value
        elif file_value:
            expected = file_value
        else:
            expected = DEFAULT_MODEL_ID

        assert config.bedrock_model_id == expected

    @given(
        env_value=_value_strategy,
        file_value=_value_strategy,
    )
    @settings(max_examples=100)
    def test_log_level_precedence_env_over_file(
        self, env_value: str | None, file_value: str | None
    ):
        """Feature: strands-bedrock-agent, Property 2: Configuration precedence is monotone

        For log_level: env > file > default (INFO). The resolved value is the
        highest-priority non-None component (normalized to uppercase if valid,
        else falls back to INFO with log_level_was_invalid=True).

        Validates: Requirements 3.2, 3.3, 4.2
        """
        from strands_bedrock_agent.config import VALID_LOG_LEVELS, DEFAULT_LOG_LEVEL

        env = {"AWS_REGION": "us-east-1"}
        if env_value is not None:
            env["LOG_LEVEL"] = env_value

        file_path = None
        if file_value is not None:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            json.dump({"log_level": file_value}, tmp)
            tmp.close()
            file_path = Path(tmp.name)

        with patch(
            "strands_bedrock_agent.config._resolve_boto3_profile_region",
            return_value=None,
        ):
            config = load_config(env=env, file_path=file_path)

        # Determine which raw value wins based on precedence (env > file > None)
        # The config module uses `or` chaining, so empty strings are treated as absent
        if env_value:
            raw_winner = env_value
        elif file_value:
            raw_winner = file_value
        else:
            raw_winner = None

        # Now apply the log level normalization logic
        if raw_winner is not None:
            normalized = raw_winner.strip().upper()
            if normalized in VALID_LOG_LEVELS:
                assert config.log_level == normalized
                assert config.log_level_was_invalid is False
            else:
                assert config.log_level == DEFAULT_LOG_LEVEL
                assert config.log_level_was_invalid is True
        else:
            assert config.log_level == DEFAULT_LOG_LEVEL
            assert config.log_level_was_invalid is False

    @given(
        env_value=_value_strategy,
        file_value=_value_strategy,
    )
    @settings(max_examples=100)
    def test_aws_region_precedence_env_over_file(
        self, env_value: str | None, file_value: str | None
    ):
        """Feature: strands-bedrock-agent, Property 2: Configuration precedence is monotone

        For aws_region: env (AWS_REGION) > env (AWS_DEFAULT_REGION) > boto3 profile.
        When all sources are None, ConfigError is raised for this required knob.

        Validates: Requirements 3.2, 3.3, 4.2
        """
        import re
        from strands_bedrock_agent.config import AWS_REGION_RE

        # Only use valid region-shaped strings for env_value and file_value
        # to test precedence cleanly (invalid formats are rejected by regex)
        # We'll use a fixed valid region format for testing precedence
        valid_regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]

        env = {}
        # Use env_value as AWS_REGION if it matches region format
        if env_value is not None and re.match(AWS_REGION_RE, env_value):
            env["AWS_REGION"] = env_value

        # Use file_value as AWS_DEFAULT_REGION (second env source for region)
        if file_value is not None and re.match(AWS_REGION_RE, file_value):
            env["AWS_DEFAULT_REGION"] = file_value

        # Determine if we have any valid region source
        has_env_region = env_value is not None and re.match(AWS_REGION_RE, env_value)
        has_default_region = file_value is not None and re.match(
            AWS_REGION_RE, file_value
        )

        with patch(
            "strands_bedrock_agent.config._resolve_boto3_profile_region",
            return_value=None,
        ):
            if has_env_region:
                config = load_config(env=env)
                assert config.aws_region == env_value
            elif has_default_region:
                config = load_config(env=env)
                assert config.aws_region == file_value
            else:
                # All sources are None for this required knob -> ConfigError
                with pytest.raises(ConfigError) as exc_info:
                    load_config(env=env)
                assert exc_info.value.knob == "aws_region"

    @settings(max_examples=100)
    @given(
        env_value=_value_strategy,
        file_value=_value_strategy,
    )
    def test_mcp_config_path_precedence(
        self, env_value: str | None, file_value: str | None
    ):
        """Feature: strands-bedrock-agent, Property 2: Configuration precedence is monotone

        For mcp_config_path: env (MCP_CONFIG_PATH) > file > default.
        The resolved value is the highest-priority non-None component.

        Validates: Requirements 3.2, 3.3, 4.2
        """
        from strands_bedrock_agent.config import DEFAULT_MCP_CONFIG_PATH

        env = {"AWS_REGION": "us-east-1"}
        if env_value is not None:
            env["MCP_CONFIG_PATH"] = env_value

        file_path = None
        if file_value is not None:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            json.dump({"mcp_config_path": file_value}, tmp)
            tmp.close()
            file_path = Path(tmp.name)

        with patch(
            "strands_bedrock_agent.config._resolve_boto3_profile_region",
            return_value=None,
        ):
            config = load_config(env=env, file_path=file_path)

        # Determine expected based on precedence: env > file > default
        if env_value:
            expected = Path(env_value)
        elif file_value:
            expected = Path(file_value)
        else:
            expected = DEFAULT_MCP_CONFIG_PATH

        assert config.mcp_config_path == expected

    @settings(max_examples=100)
    @given(
        env_value=one_of(none(), text(min_size=1, max_size=256)),
        file_value=one_of(none(), text(min_size=1, max_size=256)),
    )
    def test_all_none_required_knob_raises_config_error(
        self, env_value: str | None, file_value: str | None
    ):
        """Feature: strands-bedrock-agent, Property 2: Configuration precedence is monotone

        When all sources are None for a required knob (aws_region), ConfigError
        is raised. This tests the None-triple case for required configuration.

        Validates: Requirements 3.2, 3.3, 4.2
        """
        import re
        from strands_bedrock_agent.config import AWS_REGION_RE

        # Ensure neither value is a valid region (so region resolution fails)
        assume(env_value is None or not re.match(AWS_REGION_RE, env_value))
        assume(file_value is None or not re.match(AWS_REGION_RE, file_value))

        env = {}
        if env_value is not None:
            env["AWS_REGION"] = env_value
        if file_value is not None:
            env["AWS_DEFAULT_REGION"] = file_value

        with patch(
            "strands_bedrock_agent.config._resolve_boto3_profile_region",
            return_value=None,
        ):
            with pytest.raises(ConfigError) as exc_info:
                load_config(env=env)

            assert exc_info.value.knob == "aws_region"
            # The checked tuple should contain the sources that were examined
            assert len(exc_info.value.checked) > 0
