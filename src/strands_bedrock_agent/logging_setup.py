"""Structured JSON logging for strands-bedrock-agent.

Configures the root logger to emit single-line structured JSON records to stderr.
Provides redaction helpers for sensitive fields at different log levels.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Event-name constants
# ---------------------------------------------------------------------------

EVENT_CONFIG_RESOLVED: str = "config.resolved"
EVENT_BEDROCK_INVOKE_START: str = "bedrock.invoke.start"
EVENT_BEDROCK_INVOKE_END: str = "bedrock.invoke.end"
EVENT_BEDROCK_RETRY: str = "bedrock.retry"
EVENT_MCP_CONNECT: str = "mcp.connect"
EVENT_MCP_TOOL_START: str = "mcp.tool.start"
EVENT_MCP_TOOL_END: str = "mcp.tool.end"
EVENT_AGENT_ERROR: str = "agent.error"

# ---------------------------------------------------------------------------
# Truncation / redaction constants
# ---------------------------------------------------------------------------

PROMPT_TRUNCATION_LIMIT: int = 4096
TRUNCATION_MARKER: str = "\u2026[truncated]"

# Fields that are redacted at INFO+ levels and truncated at DEBUG level
_PROTECTED_FIELDS: set[str] = {"prompt", "tool_args", "tool_result"}

# Valid log levels (imported concept from config.py, duplicated here to avoid
# circular imports)
_VALID_LOG_LEVELS: set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record.

    Record shape:
        {"ts": "<ISO 8601 UTC>", "level": "<LEVEL>", "event": "<event_name>",
         "logger": "<logger_name>", ...extra fields...}
    """

    def format(self, record: logging.LogRecord) -> str:
        output: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
            "logger": record.name,
        }

        # Merge any extra fields attached to the record
        extra: dict[str, Any] = getattr(record, "extra_fields", {})
        if extra:
            output.update(extra)

        return json.dumps(output, default=str)


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


def configure_logging(
    level: str, log_level_was_invalid: bool, *, original_value: str = ""
) -> None:
    """Install a JSON formatter on the root logger and set the log level.

    If *log_level_was_invalid* is True, emits exactly one WARNING record
    naming LOG_LEVEL and the invalid value (R7.3).

    Args:
        level: The resolved log level string (already uppercased/stripped by
               config.py, but we normalise again defensively).
        log_level_was_invalid: Whether the original LOG_LEVEL env var was
                               invalid (triggers a warning).
        original_value: The original invalid LOG_LEVEL value (for the warning
                        message). Only used when log_level_was_invalid is True.
    """
    # Normalise level
    normalized = level.strip().upper() if level else "INFO"
    if normalized not in _VALID_LOG_LEVELS:
        normalized = "INFO"

    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, normalized))

    # Remove existing handlers to avoid duplicate output
    root_logger.handlers.clear()

    # Install a stderr handler with the JSON formatter
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)

    # Emit exactly one WARNING if the original LOG_LEVEL was invalid
    if log_level_was_invalid:
        msg = (
            f"Invalid LOG_LEVEL value {original_value!r}; falling back to INFO"
        )
        root_logger.warning(
            msg,
            extra={
                "event": "config.log_level_invalid",
                "extra_fields": {
                    "env_var": "LOG_LEVEL",
                    "invalid_value": original_value,
                },
            },
        )


# ---------------------------------------------------------------------------
# Redaction helpers
# ---------------------------------------------------------------------------


def redact_for_debug(field_name: str, value: Any) -> Any:
    """Truncate string values exceeding PROMPT_TRUNCATION_LIMIT (Property 8).

    For protected fields (prompt, tool_args, tool_result), if the value is a
    string longer than 4096 characters, return the first 4096 characters with
    TRUNCATION_MARKER appended. Non-string values and short strings are
    returned unchanged.
    """
    if field_name not in _PROTECTED_FIELDS:
        return value
    if not isinstance(value, str):
        return value
    if len(value) <= PROMPT_TRUNCATION_LIMIT:
        return value
    return value[:PROMPT_TRUNCATION_LIMIT] + TRUNCATION_MARKER


def redact_for_info(record_dict: dict[str, Any]) -> dict[str, Any]:
    """Redact protected fields for INFO+ levels (Property 9).

    Drops keys in {"prompt", "tool_args", "tool_result"} and replaces them
    with <key>_bytes = len(value.encode("utf-8")), preserving every other key.

    Returns a new dict (does not mutate the input).
    """
    result: dict[str, Any] = {}
    for key, value in record_dict.items():
        if key in _PROTECTED_FIELDS:
            # Replace with byte-length field
            if isinstance(value, str):
                result[f"{key}_bytes"] = len(value.encode("utf-8"))
            else:
                # For non-string values, encode their string representation
                result[f"{key}_bytes"] = len(str(value).encode("utf-8"))
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------


def log_event(
    logger: logging.Logger, level: int, event: str, **fields: Any
) -> None:
    """Emit a structured log record with redaction based on level.

    At DEBUG level: protected fields are truncated at 4096 chars.
    At INFO+ levels: protected fields are replaced by <key>_bytes.

    Args:
        logger: The logger instance to emit through.
        level: The numeric log level (e.g., logging.INFO).
        event: The event name constant (e.g., EVENT_BEDROCK_INVOKE_START).
        **fields: Additional event-specific fields.
    """
    if not logger.isEnabledFor(level):
        return

    # Apply redaction based on effective level
    if level <= logging.DEBUG:
        # DEBUG: truncate large protected fields
        processed_fields = {
            k: redact_for_debug(k, v) for k, v in fields.items()
        }
    else:
        # INFO+: replace protected fields with byte counts
        processed_fields = redact_for_info(fields)

    # Emit the record with extra fields attached
    logger.log(
        level,
        event,
        extra={"event": event, "extra_fields": processed_fields},
    )
