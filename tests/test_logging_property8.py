"""Property-based tests for DEBUG truncation (Property 8).

Feature: strands-bedrock-agent, Property 8: DEBUG truncation property

Validates: Requirements 7.4
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis.strategies import sampled_from, text

from strands_bedrock_agent.logging_setup import (
    PROMPT_TRUNCATION_LIMIT,
    TRUNCATION_MARKER,
    redact_for_debug,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Protected fields that undergo DEBUG truncation
_PROTECTED_FIELDS = sampled_from(["prompt", "tool_args", "tool_result"])

# Arbitrary text strings up to 10000 characters
_arbitrary_text = text(min_size=0, max_size=10000)


# ---------------------------------------------------------------------------
# Property 8: DEBUG truncation property
# ---------------------------------------------------------------------------


class TestDebugTruncationProperty:
    """Feature: strands-bedrock-agent, Property 8: DEBUG truncation property"""

    @given(s=_arbitrary_text, field=_PROTECTED_FIELDS)
    @settings(max_examples=100)
    def test_short_strings_returned_unchanged(self, s: str, field: str):
        """Feature: strands-bedrock-agent, Property 8: DEBUG truncation property

        For any string s where len(s) <= 4096, output equals s unchanged.

        Validates: Requirements 7.4
        """
        if len(s) <= PROMPT_TRUNCATION_LIMIT:
            result = redact_for_debug(field, s)
            assert result == s, (
                f"Expected short string to be returned unchanged.\n"
                f"  field: {field!r}\n"
                f"  len(s): {len(s)}\n"
                f"  result != s"
            )

    @given(s=_arbitrary_text, field=_PROTECTED_FIELDS)
    @settings(max_examples=100)
    def test_long_strings_truncated_with_marker(self, s: str, field: str):
        """Feature: strands-bedrock-agent, Property 8: DEBUG truncation property

        For any string s where len(s) > 4096, output equals
        s[:4096] + TRUNCATION_MARKER.

        Validates: Requirements 7.4
        """
        if len(s) > PROMPT_TRUNCATION_LIMIT:
            result = redact_for_debug(field, s)
            expected = s[:PROMPT_TRUNCATION_LIMIT] + TRUNCATION_MARKER
            assert result == expected, (
                f"Expected truncated string with marker.\n"
                f"  field: {field!r}\n"
                f"  len(s): {len(s)}\n"
                f"  expected len: {len(expected)}\n"
                f"  actual len: {len(result)}"
            )

    @given(s=_arbitrary_text, field=_PROTECTED_FIELDS)
    @settings(max_examples=100)
    def test_prefix_preservation(self, s: str, field: str):
        """Feature: strands-bedrock-agent, Property 8: DEBUG truncation property

        Prefix preservation: the first min(len(s), 4096) characters of the
        output match the first min(len(s), 4096) characters of the input.

        Validates: Requirements 7.4
        """
        result = redact_for_debug(field, s)
        prefix_len = min(len(s), PROMPT_TRUNCATION_LIMIT)
        assert result[:prefix_len] == s[:prefix_len], (
            f"Prefix preservation violated.\n"
            f"  field: {field!r}\n"
            f"  len(s): {len(s)}\n"
            f"  prefix_len: {prefix_len}\n"
            f"  result[:prefix_len] != s[:prefix_len]"
        )
