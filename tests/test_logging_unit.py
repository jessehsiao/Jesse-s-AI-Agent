"""Example-based unit tests for logging_setup.py.

Verifies exact JSON shapes and field presence for specific log events.

Requirements: 7.1, 7.5, 7.6
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from strands_bedrock_agent.logging_setup import (
    EVENT_AGENT_ERROR,
    EVENT_BEDROCK_INVOKE_START,
    EVENT_BEDROCK_RETRY,
    JsonFormatter,
    _PROTECTED_FIELDS,
    log_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class CaptureHandler(logging.Handler):
    """Captures formatted log output into a list."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


def _make_logger(level: int = logging.DEBUG) -> tuple[logging.Logger, CaptureHandler]:
    """Create an isolated logger with a CaptureHandler using JsonFormatter."""
    logger = logging.getLogger(f"test.unit.logging.{id(object())}")
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False

    handler = CaptureHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger, handler


# ---------------------------------------------------------------------------
# Tests: EVENT_BEDROCK_INVOKE_START at INFO level (R7.1, R7.5)
# ---------------------------------------------------------------------------


class TestBedrockInvokeStartInfoLevel:
    """Verify the exact JSON shape of an EVENT_BEDROCK_INVOKE_START record at INFO."""

    def test_info_record_has_required_base_keys(self) -> None:
        """At INFO level, the record must contain ts, level, event, logger."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.INFO,
            EVENT_BEDROCK_INVOKE_START,
            model_id="us.anthropic.claude-opus-4-5-20251101-v1:0",
            region="us-west-2",
            prompt="Hello, how are you?",
        )

        assert len(handler.records) == 1
        record = json.loads(handler.records[0])

        # Base keys present and correct types
        assert "ts" in record
        assert isinstance(record["ts"], str)
        assert "level" in record
        assert record["level"] == "INFO"
        assert "event" in record
        assert record["event"] == "bedrock.invoke.start"
        assert "logger" in record
        assert isinstance(record["logger"], str)

    def test_info_record_replaces_prompt_with_prompt_bytes(self) -> None:
        """At INFO level, prompt is replaced by prompt_bytes (R7.5)."""
        logger, handler = _make_logger(logging.DEBUG)

        prompt_text = "What is Amazon S3?"
        log_event(
            logger,
            logging.INFO,
            EVENT_BEDROCK_INVOKE_START,
            model_id="us.anthropic.claude-opus-4-5-20251101-v1:0",
            region="us-west-2",
            prompt=prompt_text,
        )

        record = json.loads(handler.records[0])

        # prompt must NOT be present
        assert "prompt" not in record
        # prompt_bytes must be present with correct value
        assert "prompt_bytes" in record
        assert record["prompt_bytes"] == len(prompt_text.encode("utf-8"))

    def test_info_record_preserves_non_protected_fields(self) -> None:
        """At INFO level, non-protected fields (model_id, region) are preserved."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.INFO,
            EVENT_BEDROCK_INVOKE_START,
            model_id="us.anthropic.claude-opus-4-5-20251101-v1:0",
            region="us-west-2",
            prompt="test prompt",
        )

        record = json.loads(handler.records[0])

        assert record["model_id"] == "us.anthropic.claude-opus-4-5-20251101-v1:0"
        assert record["region"] == "us-west-2"

    def test_info_record_exact_shape(self) -> None:
        """The full INFO record has exactly the expected set of keys."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.INFO,
            EVENT_BEDROCK_INVOKE_START,
            model_id="test-model",
            region="us-east-1",
            prompt="Hello",
        )

        record = json.loads(handler.records[0])

        expected_keys = {"ts", "level", "event", "logger", "model_id", "region", "prompt_bytes"}
        assert set(record.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Tests: EVENT_BEDROCK_INVOKE_START at DEBUG level (R7.1, R7.4)
# ---------------------------------------------------------------------------


class TestBedrockInvokeStartDebugLevel:
    """Verify the exact JSON shape of an EVENT_BEDROCK_INVOKE_START record at DEBUG."""

    def test_debug_record_includes_prompt_field(self) -> None:
        """At DEBUG level, prompt is included (possibly truncated) instead of prompt_bytes."""
        logger, handler = _make_logger(logging.DEBUG)

        prompt_text = "What is Amazon S3?"
        log_event(
            logger,
            logging.DEBUG,
            EVENT_BEDROCK_INVOKE_START,
            model_id="us.anthropic.claude-opus-4-5-20251101-v1:0",
            region="us-west-2",
            prompt=prompt_text,
        )

        assert len(handler.records) == 1
        record = json.loads(handler.records[0])

        # At DEBUG, prompt is kept (not replaced by prompt_bytes)
        assert "prompt" in record
        assert record["prompt"] == prompt_text
        assert "prompt_bytes" not in record

    def test_debug_record_truncates_long_prompt(self) -> None:
        """At DEBUG level, prompt longer than 4096 chars is truncated with marker."""
        logger, handler = _make_logger(logging.DEBUG)

        long_prompt = "x" * 5000
        log_event(
            logger,
            logging.DEBUG,
            EVENT_BEDROCK_INVOKE_START,
            model_id="test-model",
            region="us-east-1",
            prompt=long_prompt,
        )

        record = json.loads(handler.records[0])

        assert "prompt" in record
        assert record["prompt"].startswith("x" * 4096)
        assert record["prompt"].endswith("\u2026[truncated]")
        assert len(record["prompt"]) == 4096 + len("\u2026[truncated]")

    def test_debug_record_has_required_base_keys(self) -> None:
        """At DEBUG level, the record still has ts, level, event, logger."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.DEBUG,
            EVENT_BEDROCK_INVOKE_START,
            model_id="test-model",
            region="us-east-1",
            prompt="short prompt",
        )

        record = json.loads(handler.records[0])

        assert record["level"] == "DEBUG"
        assert record["event"] == "bedrock.invoke.start"
        assert "ts" in record
        assert "logger" in record

    def test_debug_record_exact_shape(self) -> None:
        """The full DEBUG record has exactly the expected set of keys."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.DEBUG,
            EVENT_BEDROCK_INVOKE_START,
            model_id="test-model",
            region="us-east-1",
            prompt="Hello",
        )

        record = json.loads(handler.records[0])

        expected_keys = {"ts", "level", "event", "logger", "model_id", "region", "prompt"}
        assert set(record.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Tests: EVENT_BEDROCK_RETRY carries attempt and aws_error_code (R7.6)
# ---------------------------------------------------------------------------


class TestBedrockRetryRecord:
    """Verify that a bedrock.retry record carries attempt and aws_error_code."""

    def test_retry_record_has_attempt_field(self) -> None:
        """A bedrock.retry record must include the attempt number."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.WARNING,
            EVENT_BEDROCK_RETRY,
            model_id="us.anthropic.claude-opus-4-5-20251101-v1:0",
            attempt=2,
            aws_error_code="ThrottlingException",
        )

        record = json.loads(handler.records[0])

        assert "attempt" in record
        assert record["attempt"] == 2

    def test_retry_record_has_aws_error_code_field(self) -> None:
        """A bedrock.retry record must include the aws_error_code."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.WARNING,
            EVENT_BEDROCK_RETRY,
            model_id="us.anthropic.claude-opus-4-5-20251101-v1:0",
            attempt=1,
            aws_error_code="ServiceUnavailableException",
        )

        record = json.loads(handler.records[0])

        assert "aws_error_code" in record
        assert record["aws_error_code"] == "ServiceUnavailableException"

    def test_retry_record_event_name(self) -> None:
        """The event field must be 'bedrock.retry'."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.WARNING,
            EVENT_BEDROCK_RETRY,
            model_id="test-model",
            attempt=3,
            aws_error_code="ThrottlingException",
        )

        record = json.loads(handler.records[0])

        assert record["event"] == "bedrock.retry"
        assert record["level"] == "WARNING"

    def test_retry_record_preserves_model_id(self) -> None:
        """The retry record preserves the model_id field."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.WARNING,
            EVENT_BEDROCK_RETRY,
            model_id="us.anthropic.claude-opus-4-5-20251101-v1:0",
            attempt=1,
            aws_error_code="ThrottlingException",
        )

        record = json.loads(handler.records[0])

        assert record["model_id"] == "us.anthropic.claude-opus-4-5-20251101-v1:0"


# ---------------------------------------------------------------------------
# Tests: agent.error records exclude protected fields (R7.5)
# ---------------------------------------------------------------------------


class TestAgentErrorNoProtectedFields:
    """Verify that agent.error records do not include keys from the protected set."""

    def test_error_record_excludes_prompt(self) -> None:
        """An agent.error record at ERROR level must not contain 'prompt'."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.ERROR,
            EVENT_AGENT_ERROR,
            category="bedrock",
            message="Model invocation failed",
            prompt="This is a secret prompt that should be redacted",
        )

        record = json.loads(handler.records[0])

        assert "prompt" not in record
        # Should have prompt_bytes instead
        assert "prompt_bytes" in record

    def test_error_record_excludes_tool_args(self) -> None:
        """An agent.error record at ERROR level must not contain 'tool_args'."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.ERROR,
            EVENT_AGENT_ERROR,
            category="mcp",
            message="Tool call failed",
            tool_args='{"query": "sensitive search"}',
        )

        record = json.loads(handler.records[0])

        assert "tool_args" not in record
        assert "tool_args_bytes" in record

    def test_error_record_excludes_tool_result(self) -> None:
        """An agent.error record at ERROR level must not contain 'tool_result'."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.ERROR,
            EVENT_AGENT_ERROR,
            category="mcp",
            message="Tool returned error",
            tool_result="Some sensitive tool output data",
        )

        record = json.loads(handler.records[0])

        assert "tool_result" not in record
        assert "tool_result_bytes" in record

    def test_error_record_excludes_all_protected_fields_simultaneously(self) -> None:
        """An agent.error record must not contain any key from the protected set."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.ERROR,
            EVENT_AGENT_ERROR,
            category="unhandled",
            message="Unexpected error",
            prompt="secret prompt",
            tool_args="secret args",
            tool_result="secret result",
        )

        record = json.loads(handler.records[0])

        # None of the protected fields should be present
        for protected_key in _PROTECTED_FIELDS:
            assert protected_key not in record, (
                f"Protected key {protected_key!r} found in agent.error record"
            )

        # All should be replaced with _bytes variants
        assert "prompt_bytes" in record
        assert "tool_args_bytes" in record
        assert "tool_result_bytes" in record

    def test_error_record_preserves_category_and_message(self) -> None:
        """Non-protected fields like category and message are preserved in error records."""
        logger, handler = _make_logger(logging.DEBUG)

        log_event(
            logger,
            logging.ERROR,
            EVENT_AGENT_ERROR,
            category="bedrock",
            message="ThrottlingException after retries exhausted",
            prompt="some prompt",
        )

        record = json.loads(handler.records[0])

        assert record["category"] == "bedrock"
        assert record["message"] == "ThrottlingException after retries exhausted"
        assert record["event"] == "agent.error"
