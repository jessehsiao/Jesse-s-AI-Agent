"""Property-based tests for diagnostic completeness (Property 3).

Feature: strands-bedrock-agent, Property 3: Diagnostic completeness for missing required values

Validates: Requirements 3.5, 4.3
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis.strategies import (
    booleans,
    none,
    one_of,
    text,
)

from strands_bedrock_agent.config import load_config, AWS_REGION_RE
from strands_bedrock_agent.errors import ConfigError


# ---------------------------------------------------------------------------
# Canonical source names that must appear in ConfigError.checked for aws_region
# ---------------------------------------------------------------------------

# These are the exact source labels used in config.py's region resolution path.
REGION_CANONICAL_SOURCES = (
    "cli_overrides['region']",
    "env['AWS_REGION']",
    "env['AWS_DEFAULT_REGION']",
    "boto3_profile_region",
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate strings that do NOT match a valid AWS region pattern, or None.
# This ensures region resolution always fails.
_invalid_region_or_none = one_of(
    none(),
    text(min_size=0, max_size=256),
)


# ---------------------------------------------------------------------------
# Property 3: Diagnostic completeness for missing required values
# ---------------------------------------------------------------------------


class TestDiagnosticCompleteness:
    """Feature: strands-bedrock-agent, Property 3: Diagnostic completeness for missing required values"""

    @given(
        cli_region=_invalid_region_or_none,
        env_aws_region=_invalid_region_or_none,
        env_default_region=_invalid_region_or_none,
        boto3_region=_invalid_region_or_none,
    )
    @settings(max_examples=100)
    def test_aws_region_error_contains_all_checked_sources(
        self,
        cli_region: str | None,
        env_aws_region: str | None,
        env_default_region: str | None,
        boto3_region: str | None,
    ):
        """Feature: strands-bedrock-agent, Property 3: Diagnostic completeness for missing required values

        When aws_region cannot be resolved from any source, the ConfigError
        raised by load_config carries a `checked` tuple that contains every
        canonical source name. No source is omitted from the diagnostic.

        Validates: Requirements 3.5, 4.3
        """
        # Ensure none of the generated values match a valid region pattern
        assume(cli_region is None or not re.match(AWS_REGION_RE, cli_region))
        assume(env_aws_region is None or not re.match(AWS_REGION_RE, env_aws_region))
        assume(env_default_region is None or not re.match(AWS_REGION_RE, env_default_region))
        assume(boto3_region is None or not re.match(AWS_REGION_RE, boto3_region))

        # Build the env dict with whatever invalid values were generated
        env: dict[str, str] = {}
        if env_aws_region is not None:
            env["AWS_REGION"] = env_aws_region
        if env_default_region is not None:
            env["AWS_DEFAULT_REGION"] = env_default_region

        # Build CLI overrides
        cli_overrides: dict[str, str] | None = None
        if cli_region is not None:
            cli_overrides = {"region": cli_region}

        # Mock boto3 profile region to return the generated (invalid) value
        with patch(
            "strands_bedrock_agent.config._resolve_boto3_profile_region",
            return_value=boto3_region,
        ):
            with pytest.raises(ConfigError) as exc_info:
                load_config(cli_overrides=cli_overrides, env=env)

        error = exc_info.value

        # Property assertion 1: The error names the correct knob
        assert error.knob == "aws_region"

        # Property assertion 2: The checked tuple contains ALL canonical sources
        for source in REGION_CANONICAL_SOURCES:
            assert source in error.checked, (
                f"Source '{source}' missing from checked tuple: {error.checked}"
            )

        # Property assertion 3: The error message contains the knob name
        assert "aws_region" in str(error)

        # Property assertion 4: The error message contains every checked source
        error_message = str(error)
        for source in error.checked:
            assert source in error_message, (
                f"Source '{source}' not mentioned in error message: {error_message}"
            )

    @given(
        env_aws_region=_invalid_region_or_none,
        env_default_region=_invalid_region_or_none,
    )
    @settings(max_examples=100)
    def test_aws_region_error_checked_tuple_is_ordered(
        self,
        env_aws_region: str | None,
        env_default_region: str | None,
    ):
        """Feature: strands-bedrock-agent, Property 3: Diagnostic completeness for missing required values

        The checked tuple preserves the resolution order: cli > env AWS_REGION >
        env AWS_DEFAULT_REGION > boto3 profile. This ensures operators can read
        the diagnostic top-to-bottom in priority order.

        Validates: Requirements 3.5, 4.3
        """
        # Ensure none of the generated values match a valid region pattern
        assume(env_aws_region is None or not re.match(AWS_REGION_RE, env_aws_region))
        assume(env_default_region is None or not re.match(AWS_REGION_RE, env_default_region))

        env: dict[str, str] = {}
        if env_aws_region is not None:
            env["AWS_REGION"] = env_aws_region
        if env_default_region is not None:
            env["AWS_DEFAULT_REGION"] = env_default_region

        with patch(
            "strands_bedrock_agent.config._resolve_boto3_profile_region",
            return_value=None,
        ):
            with pytest.raises(ConfigError) as exc_info:
                load_config(env=env)

        checked = exc_info.value.checked

        # The checked tuple must be exactly the canonical sources in order
        assert checked == REGION_CANONICAL_SOURCES, (
            f"Expected {REGION_CANONICAL_SOURCES}, got {checked}"
        )

    @given(
        has_cli=booleans(),
        has_env_region=booleans(),
        has_env_default=booleans(),
        has_boto3=booleans(),
    )
    @settings(max_examples=100)
    def test_aws_region_all_absent_subsets_report_all_sources(
        self,
        has_cli: bool,
        has_env_region: bool,
        has_env_default: bool,
        has_boto3: bool,
    ):
        """Feature: strands-bedrock-agent, Property 3: Diagnostic completeness for missing required values

        For every subset of sources {cli, env, env_default, profile} being
        absent (None vs present-but-invalid), the ConfigError.checked tuple
        always contains all four canonical source names, because the resolution
        logic checks every source regardless of whether a value was provided.

        Validates: Requirements 3.5, 4.3
        """
        # Build inputs: either None (absent) or an invalid string (present but invalid)
        cli_overrides: dict | None = None
        if has_cli:
            cli_overrides = {"region": "not-a-region"}

        env: dict[str, str] = {}
        if has_env_region:
            env["AWS_REGION"] = "invalid!"
        if has_env_default:
            env["AWS_DEFAULT_REGION"] = "also_invalid"

        boto3_return = "nope" if has_boto3 else None

        with patch(
            "strands_bedrock_agent.config._resolve_boto3_profile_region",
            return_value=boto3_return,
        ):
            with pytest.raises(ConfigError) as exc_info:
                load_config(cli_overrides=cli_overrides, env=env)

        error = exc_info.value
        assert error.knob == "aws_region"

        # Regardless of which sources are present-but-invalid vs absent,
        # ALL canonical sources must appear in the checked tuple
        for source in REGION_CANONICAL_SOURCES:
            assert source in error.checked, (
                f"Source '{source}' missing from checked tuple: {error.checked}"
            )
