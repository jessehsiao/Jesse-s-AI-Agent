"""Property-based tests for LOG_LEVEL resolution partition (Property 7).

Feature: strands-bedrock-agent, Property 7: LOG_LEVEL resolution partition

Validates: Requirements 7.2, 7.3
"""

from __future__ import annotations

import logging

from hypothesis import given, settings, assume
from hypothesis.strategies import (
    sampled_from,
    text,
)

from strands_bedrock_agent.logging_setup import (
    _VALID_LOG_LEVELS,
    configure_logging,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy that generates valid log levels with mixed case
_VALID_LEVELS_LIST = list(_VALID_LOG_LEVELS)


def _mixed_case_valid_level():
    """Strategy that produces valid log level strings with arbitrary casing."""
    return sampled_from(_VALID_LEVELS_LIST).flatmap(
        lambda level: sampled_from(
            [
                level.lower(),
                level.upper(),
                level.capitalize(),
                level.swapcase(),
                level[0].lower() + level[1:].upper(),
            ]
        )
    )


# Strategy for arbitrary text (may be valid or invalid)
_arbitrary_text = text(min_size=0, max_size=200)


# ---------------------------------------------------------------------------
# Property 7: LOG_LEVEL resolution partition
# ---------------------------------------------------------------------------


class TestLogLevelResolutionPartition:
    """Feature: strands-bedrock-agent, Property 7: LOG_LEVEL resolution partition"""

    @given(level_str=_mixed_case_valid_level())
    @settings(max_examples=100)
    def test_valid_level_sets_root_and_emits_no_log_level_warning(
        self, level_str: str
    ):
        """Feature: strands-bedrock-agent, Property 7: LOG_LEVEL resolution partition

        Valid levels (any case) set the root level and emit zero LOG_LEVEL
        warnings.

        Validates: Requirements 7.2, 7.3
        """
        configure_logging(level_str, log_level_was_invalid=False)

        root = logging.getLogger()

        # The root logger level should be set to the uppercased version
        expected_level = getattr(logging, level_str.strip().upper())
        assert root.level == expected_level, (
            f"Expected root level {expected_level} "
            f"({level_str.strip().upper()}) but got {root.level} "
            f"({logging.getLevelName(root.level)})"
        )

    @given(level_str=_arbitrary_text)
    @settings(max_examples=100)
    def test_invalid_nonempty_level_falls_back_to_info_with_warning(
        self, level_str: str
    ):
        """Feature: strands-bedrock-agent, Property 7: LOG_LEVEL resolution partition

        Invalid non-empty values fall back to INFO and emit exactly one
        WARNING containing the offending value verbatim and the literal
        `LOG_LEVEL`.

        Validates: Requirements 7.2, 7.3
        """
        # Skip valid levels (any case) and empty/whitespace-only strings
        normalized = level_str.strip().upper()
        assume(normalized not in _VALID_LOG_LEVELS)
        assume(len(level_str.strip()) > 0)  # non-empty after strip

        # We need to capture the WARNING emitted during configure_logging.
        # configure_logging clears existing handlers and installs its own
        # StreamHandler. To capture records, we'll install a custom handler
        # class that records everything, then call configure_logging which
        # will clear it and install its own. But the WARNING is emitted
        # AFTER the handler is installed, so we can add our capturing handler
        # after configure_logging sets up, but before the warning is emitted.
        #
        # Looking at the implementation: configure_logging:
        # 1. Normalizes level
        # 2. Sets root level
        # 3. Clears handlers
        # 4. Installs StreamHandler with JsonFormatter
        # 5. If log_level_was_invalid: emits WARNING
        #
        # So the WARNING goes through the newly installed handler.
        # We can capture it by adding our handler BEFORE calling configure_logging
        # and it will be cleared. Instead, let's add it AFTER but that misses
        # the warning too since it's already emitted.
        #
        # Best approach: patch the root logger to use a capturing handler that
        # survives the clear, OR check the StreamHandler's output.
        #
        # Simplest: We'll use a logging filter on the root logger that captures
        # records. Filters are NOT cleared by handlers.clear().

        class RecordCapture(logging.Filter):
            def __init__(self):
                super().__init__()
                self.records: list[logging.LogRecord] = []

            def filter(self, record: logging.LogRecord) -> bool:
                self.records.append(record)
                return True

        root = logging.getLogger()
        capture = RecordCapture()
        root.addFilter(capture)

        try:
            configure_logging(
                level_str,
                log_level_was_invalid=True,
                original_value=level_str,
            )

            # Root level should fall back to INFO
            assert root.level == logging.INFO, (
                f"Expected root level INFO ({logging.INFO}) "
                f"but got {root.level} ({logging.getLevelName(root.level)}) "
                f"for invalid level {level_str!r}"
            )

            # Exactly one WARNING record should have been emitted
            warning_records = [
                r for r in capture.records if r.levelno == logging.WARNING
            ]
            assert len(warning_records) == 1, (
                f"Expected exactly 1 WARNING record but got "
                f"{len(warning_records)} for invalid level {level_str!r}"
            )

            # The warning message must contain the offending value verbatim.
            # The implementation uses repr() formatting for the value, so
            # we check that repr(level_str) appears in the message.
            warning_msg = warning_records[0].getMessage()
            assert repr(level_str) in warning_msg or level_str in warning_msg, (
                f"WARNING message {warning_msg!r} does not contain "
                f"the offending value {level_str!r} verbatim"
            )

            # The warning message must contain the literal "LOG_LEVEL"
            assert "LOG_LEVEL" in warning_msg, (
                f"WARNING message {warning_msg!r} does not contain "
                f"the literal 'LOG_LEVEL'"
            )
        finally:
            root.removeFilter(capture)

    @given(level_str=_mixed_case_valid_level())
    @settings(max_examples=100)
    def test_valid_level_any_case_emits_no_warning(self, level_str: str):
        """Feature: strands-bedrock-agent, Property 7: LOG_LEVEL resolution partition

        Valid levels in any case combination set the root level correctly
        and emit zero LOG_LEVEL warnings (verifying via filter capture).

        Validates: Requirements 7.2, 7.3
        """

        class RecordCapture(logging.Filter):
            def __init__(self):
                super().__init__()
                self.records: list[logging.LogRecord] = []

            def filter(self, record: logging.LogRecord) -> bool:
                self.records.append(record)
                return True

        root = logging.getLogger()
        capture = RecordCapture()
        root.addFilter(capture)

        try:
            configure_logging(
                level_str,
                log_level_was_invalid=False,
            )

            # Root level should be set to the valid level
            expected_level = getattr(logging, level_str.strip().upper())
            assert root.level == expected_level, (
                f"Expected root level {logging.getLevelName(expected_level)} "
                f"but got {logging.getLevelName(root.level)} "
                f"for valid level {level_str!r}"
            )

            # No WARNING records about LOG_LEVEL should have been emitted
            warning_records = [
                r for r in capture.records if r.levelno == logging.WARNING
            ]
            log_level_warnings = [
                r
                for r in warning_records
                if "LOG_LEVEL" in r.getMessage()
            ]
            assert len(log_level_warnings) == 0, (
                f"Expected zero LOG_LEVEL warnings but got "
                f"{len(log_level_warnings)} for valid level {level_str!r}"
            )
        finally:
            root.removeFilter(capture)
