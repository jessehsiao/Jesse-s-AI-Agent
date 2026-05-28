"""Property-based tests for INFO+ redaction (Property 9).

Feature: strands-bedrock-agent, Property 9: INFO+ redaction property

Validates: Requirements 7.5
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis.strategies import (
    booleans,
    dictionaries,
    fixed_dictionaries,
    just,
    none,
    one_of,
    sampled_from,
    text,
)

from strands_bedrock_agent.logging_setup import redact_for_info


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Protected keys that should be redacted at INFO+ levels
_PROTECTED_KEYS = {"prompt", "tool_args", "tool_result"}

# Arbitrary text dictionaries (no protected keys guaranteed)
_arbitrary_dicts = dictionaries(text(min_size=1, max_size=50), text(max_size=200), max_size=10)

# Strategy that generates a dict with at least one protected key injected
_protected_key = sampled_from(sorted(_PROTECTED_KEYS))
_protected_value = text(max_size=500)


# ---------------------------------------------------------------------------
# Property 9: INFO+ redaction property
# ---------------------------------------------------------------------------


class TestInfoRedactionProperty:
    """Feature: strands-bedrock-agent, Property 9: INFO+ redaction property"""

    @given(d=_arbitrary_dicts)
    @settings(max_examples=100)
    def test_non_protected_keys_preserved(self, d: dict[str, str]):
        """Feature: strands-bedrock-agent, Property 9: INFO+ redaction property

        For any dict without protected keys, redact_for_info returns an
        identical dict (all keys and values preserved unchanged).

        Validates: Requirements 7.5
        """
        # Remove any accidentally generated protected keys
        clean = {k: v for k, v in d.items() if k not in _PROTECTED_KEYS}
        result = redact_for_info(clean)
        assert result == clean, (
            f"Expected non-protected keys to be preserved unchanged.\n"
            f"  input: {clean!r}\n"
            f"  result: {result!r}"
        )

    @given(key=_protected_key, value=_protected_value)
    @settings(max_examples=100)
    def test_protected_key_replaced_with_bytes(self, key: str, value: str):
        """Feature: strands-bedrock-agent, Property 9: INFO+ redaction property

        For any protected key (prompt, tool_args, tool_result) with a string
        value, redact_for_info removes the key and adds <key>_bytes equal to
        len(value.encode("utf-8")).

        Validates: Requirements 7.5
        """
        d = {key: value}
        result = redact_for_info(d)

        # Original key must be absent
        assert key not in result, (
            f"Protected key {key!r} should be removed from result.\n"
            f"  result keys: {list(result.keys())}"
        )

        # Replacement key must be present with correct byte count
        bytes_key = f"{key}_bytes"
        assert bytes_key in result, (
            f"Expected {bytes_key!r} in result.\n"
            f"  result keys: {list(result.keys())}"
        )
        expected_bytes = len(value.encode("utf-8"))
        assert result[bytes_key] == expected_bytes, (
            f"Expected {bytes_key} == {expected_bytes}, got {result[bytes_key]}.\n"
            f"  value: {value!r}"
        )

    @given(d=_arbitrary_dicts, key=_protected_key, value=_protected_value)
    @settings(max_examples=100)
    def test_mixed_dict_preserves_non_protected_and_redacts_protected(
        self, d: dict[str, str], key: str, value: str
    ):
        """Feature: strands-bedrock-agent, Property 9: INFO+ redaction property

        For a dict containing both protected and non-protected keys,
        redact_for_info preserves every non-protected key/value and replaces
        each protected key with <key>_bytes.

        Validates: Requirements 7.5
        """
        # Build a mixed dict: inject a protected key into the arbitrary dict
        mixed = {k: v for k, v in d.items() if k not in _PROTECTED_KEYS}
        mixed[key] = value

        result = redact_for_info(mixed)

        # Non-protected keys preserved
        for k, v in mixed.items():
            if k not in _PROTECTED_KEYS:
                assert k in result, f"Non-protected key {k!r} missing from result"
                assert result[k] == v, (
                    f"Non-protected key {k!r} value changed.\n"
                    f"  expected: {v!r}\n"
                    f"  got: {result[k]!r}"
                )

        # Protected key replaced
        assert key not in result
        bytes_key = f"{key}_bytes"
        assert bytes_key in result
        assert result[bytes_key] == len(value.encode("utf-8"))

    @given(d=_arbitrary_dicts)
    @settings(max_examples=100)
    def test_result_does_not_mutate_input(self, d: dict[str, str]):
        """Feature: strands-bedrock-agent, Property 9: INFO+ redaction property

        redact_for_info returns a new dict and does not mutate the input.

        Validates: Requirements 7.5
        """
        # Inject a protected key to ensure redaction happens
        original = dict(d)
        original["prompt"] = "test value"
        snapshot = dict(original)

        _ = redact_for_info(original)

        assert original == snapshot, (
            f"Input dict was mutated by redact_for_info.\n"
            f"  before: {snapshot!r}\n"
            f"  after: {original!r}"
        )
