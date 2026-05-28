"""Property-based tests for log record structural invariant (Property 6).

Feature: strands-bedrock-agent, Property 6: Log record structural invariant

Validates: Requirements 7.1
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from hypothesis import given, settings, assume
from hypothesis.strategies import (
    dictionaries,
    integers,
    sampled_from,
    text,
)

from strands_bedrock_agent.logging_setup import (
    _VALID_LOG_LEVELS,
    _PROTECTED_FIELDS,
    JsonFormatter,
    log_event,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid Python log levels (numeric) that map to the standard level names
_NUMERIC_LEVELS = sampled_from(
    [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]
)

# Event names: non-empty strings (1-100 chars, printable ASCII for JSON safety)
_event_strategy = text(
    min_size=1,
    max_size=100,
    alphabet="abcdefghijklmnopqrstuvwxyz._",
)

# Extra fields: dictionaries with string keys and string values
# Keys are non-empty identifiers (no overlap with the base keys ts/level/event/logger)
_BASE_KEYS = {"ts", "level", "event", "logger"}

_field_key_strategy = text(
    min_size=1,
    max_size=50,
    alphabet="abcdefghijklmnopqrstuvwxyz_",
).filter(lambda k: k not in _BASE_KEYS)

_field_value_strategy = text(min_size=0, max_size=500)

_fields_strategy = dictionaries(
    keys=_field_key_strategy,
    values=_field_value_strategy,
    min_size=0,
    max_size=5,
)


# ---------------------------------------------------------------------------
# Captured-records fixture (a logging.Handler that appends to a list)
# ---------------------------------------------------------------------------


class CapturedRecordsHandler(logging.Handler):
    """A logging handler that captures formatted output strings into a list."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


def _make_captured_logger() -> tuple[logging.Logger, CapturedRecordsHandler]:
    """Create a logger with a CapturedRecordsHandler using JsonFormatter."""
    logger = logging.getLogger(f"test.property6.{id(object())}")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)  # Capture all levels
    logger.propagate = False

    handler = CapturedRecordsHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

    return logger, handler


# ---------------------------------------------------------------------------
# Property 6: Log record structural invariant
# ---------------------------------------------------------------------------


class TestLogRecordStructuralInvariant:
    """Feature: strands-bedrock-agent, Property 6: Log record structural invariant"""

    @given(
        level=_NUMERIC_LEVELS,
        event=_event_strategy,
        fields=_fields_strategy,
    )
    @settings(max_examples=100)
    def test_emitted_record_contains_required_keys_with_nonempty_strings(
        self, level: int, event: str, fields: dict[str, str]
    ):
        """Feature: strands-bedrock-agent, Property 6: Log record structural invariant

        Every emitted JSON record contains `ts`, `level`, `event`, `logger`
        as non-empty strings.

        Validates: Requirements 7.1
        """
        logger, handler = _make_captured_logger()

        log_event(logger, level, event, **fields)

        assert len(handler.records) == 1, "Expected exactly one record emitted"
        record = json.loads(handler.records[0])

        # All four base keys must be present and non-empty strings
        for key in ("ts", "level", "event", "logger"):
            assert key in record, f"Missing required key: {key}"
            assert isinstance(record[key], str), f"{key} must be a string"
            assert len(record[key]) > 0, f"{key} must be non-empty"

    @given(
        level=_NUMERIC_LEVELS,
        event=_event_strategy,
        fields=_fields_strategy,
    )
    @settings(max_examples=100)
    def test_ts_field_parses_as_iso_8601(
        self, level: int, event: str, fields: dict[str, str]
    ):
        """Feature: strands-bedrock-agent, Property 6: Log record structural invariant

        The `ts` field parses as an ISO 8601 timestamp with timezone offset.

        Validates: Requirements 7.1
        """
        logger, handler = _make_captured_logger()

        log_event(logger, level, event, **fields)

        assert len(handler.records) == 1
        record = json.loads(handler.records[0])

        ts_value = record["ts"]
        # Must parse as ISO 8601 datetime with timezone info
        parsed = datetime.fromisoformat(ts_value)
        assert parsed.tzinfo is not None, "ts must include timezone offset"

    @given(
        level=_NUMERIC_LEVELS,
        event=_event_strategy,
        fields=_fields_strategy,
    )
    @settings(max_examples=100)
    def test_level_field_is_valid_log_level(
        self, level: int, event: str, fields: dict[str, str]
    ):
        """Feature: strands-bedrock-agent, Property 6: Log record structural invariant

        The `level` field is one of the valid log levels:
        {DEBUG, INFO, WARNING, ERROR, CRITICAL}.

        Validates: Requirements 7.1
        """
        logger, handler = _make_captured_logger()

        log_event(logger, level, event, **fields)

        assert len(handler.records) == 1
        record = json.loads(handler.records[0])

        assert record["level"] in _VALID_LOG_LEVELS, (
            f"level {record['level']!r} not in {_VALID_LOG_LEVELS}"
        )

    @given(
        level=_NUMERIC_LEVELS,
        event=_event_strategy,
        fields=_fields_strategy,
    )
    @settings(max_examples=100)
    def test_additional_keys_equal_post_redaction_field_set(
        self, level: int, event: str, fields: dict[str, str]
    ):
        """Feature: strands-bedrock-agent, Property 6: Log record structural invariant

        The additional keys (beyond ts, level, event, logger) equal the
        post-redaction field set. At DEBUG level, protected fields are kept
        (possibly truncated). At INFO+ levels, protected fields are replaced
        by <key>_bytes.

        Validates: Requirements 7.1
        """
        logger, handler = _make_captured_logger()

        log_event(logger, level, event, **fields)

        assert len(handler.records) == 1
        record = json.loads(handler.records[0])

        # Compute expected additional keys based on redaction rules
        additional_keys = set(record.keys()) - _BASE_KEYS

        if level <= logging.DEBUG:
            # DEBUG: all field keys are preserved (values may be truncated)
            expected_keys = set(fields.keys())
        else:
            # INFO+: protected fields are replaced with <key>_bytes
            expected_keys = set()
            for k in fields.keys():
                if k in _PROTECTED_FIELDS:
                    expected_keys.add(f"{k}_bytes")
                else:
                    expected_keys.add(k)

        assert additional_keys == expected_keys, (
            f"Additional keys mismatch.\n"
            f"  Got:      {additional_keys}\n"
            f"  Expected: {expected_keys}\n"
            f"  Level:    {logging.getLevelName(level)}\n"
            f"  Fields:   {fields}"
        )
