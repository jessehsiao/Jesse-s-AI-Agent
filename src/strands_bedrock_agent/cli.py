"""CLI entry point for strands-bedrock-agent.

This module provides the prompt validation helper, sanitised error
rendering, argparse setup, the main() function (single-prompt and
interactive REPL modes), and a progress spinner for interactive mode.

Requirements: 2.4, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 7.7
"""

from __future__ import annotations

import argparse
import sys
import threading
from typing import TextIO

from strands_bedrock_agent.errors import (
    CATEGORY_EXIT_CODES,
    ERROR_CLASS_CATEGORY,
    EXIT_AGENT_ERROR,
    EXIT_CONFIG,
    EXIT_CREDENTIALS,
    EXIT_MODEL_UNAVAILABLE,
    EXIT_OK,
    EXIT_USAGE,
    BedrockRetryExhaustedError,
    ConfigError,
    CredentialsError,
    ModelUnavailableError,
    PromptValidationError,
    render_error,
)

# ---------------------------------------------------------------------------
# Spinner characters for progress indicator (R6.6)
# ---------------------------------------------------------------------------

_SPINNER_CHARS = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


# ---------------------------------------------------------------------------
# Prompt validation (Property 1)
# ---------------------------------------------------------------------------


def validate_prompt(s: str, max_len: int) -> str:
    """Validate and strip a user prompt.

    Returns ``s.strip()`` iff:
      - ``1 <= len(s) <= max_len``
      - ``len(s.strip()) >= 1``

    Otherwise raises ``PromptValidationError``.

    The caller MUST NOT invoke the Agent when this function raises.
    """
    if len(s) < 1 or len(s) > max_len:
        raise PromptValidationError(
            f"Prompt length must be between 1 and {max_len} characters "
            f"(got {len(s)})."
        )
    stripped = s.strip()
    if len(stripped) < 1:
        raise PromptValidationError(
            "Prompt must not be empty or whitespace-only."
        )
    return stripped


# ---------------------------------------------------------------------------
# Sanitised error output (Property 10)
# ---------------------------------------------------------------------------


def emit_error(exc: Exception, *, stream: TextIO = sys.stderr) -> None:
    """Write a sanitised, single-line error message to the given stream.

    Uses ``errors.render_error`` to strip credentials and tracebacks from
    the operator-visible message. The category is resolved from the
    exception's class via ``ERROR_CLASS_CATEGORY``; unknown classes map to
    ``"unhandled"``.
    """
    category = ERROR_CLASS_CATEGORY.get(type(exc), "unhandled")
    message = str(exc)
    line = render_error(category, message)
    stream.write(line + "\n")
    stream.flush()


# ---------------------------------------------------------------------------
# Progress indicator (R6.6)
# ---------------------------------------------------------------------------


class _ProgressSpinner:
    """Daemon thread that writes a rotating spinner to stderr.

    Used in interactive mode while the Agent is processing a prompt.
    Writes at least one spinner character per second.
    """

    def __init__(self, stream: TextIO = sys.stderr) -> None:
        self._stream = stream
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the spinner thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="cli-spinner"
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the spinner to stop and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        # Clear the spinner character from the line
        self._stream.write("\r \r")
        self._stream.flush()

    def _run(self) -> None:
        """Spinner loop: write one character per second until stopped."""
        idx = 0
        while not self._stop_event.is_set():
            char = _SPINNER_CHARS[idx % len(_SPINNER_CHARS)]
            self._stream.write(f"\r{char}")
            self._stream.flush()
            idx += 1
            # Wait up to 1 second, but check stop_event frequently
            self._stop_event.wait(timeout=1.0)


# ---------------------------------------------------------------------------
# Argparse (R6.5)
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Layout:
        strands-bedrock-agent [-h] [--prompt PROMPT] [--log-level LEVEL]
    """
    parser = argparse.ArgumentParser(
        prog="strands-bedrock-agent",
        description="AI Agent powered by Strands SDK, Claude Opus on Bedrock, "
        "and AWS Knowledge MCP tools.",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Single prompt to send (1-10000 chars). "
        "If omitted, runs in interactive mode reading one prompt per line "
        "from stdin.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        dest="log_level",
        metavar="LEVEL",
        help="Override LOG_LEVEL (DEBUG/INFO/WARNING/ERROR/CRITICAL)",
    )
    return parser


# ---------------------------------------------------------------------------
# Exit code resolution
# ---------------------------------------------------------------------------


def _exit_code_for(exc: Exception) -> int:
    """Map an exception to the appropriate CLI exit code."""
    category = ERROR_CLASS_CATEGORY.get(type(exc), "unhandled")
    return CATEGORY_EXIT_CODES.get(category, EXIT_AGENT_ERROR)


# ---------------------------------------------------------------------------
# main() (R6.1, R6.2, R6.4, R6.7, R6.8)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point declared as console_script ``strands-bedrock-agent`` (R6.1).

    Returns:
        Exit code: 0 on success, non-zero on error.
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Resolve Config
    # ------------------------------------------------------------------
    try:
        from strands_bedrock_agent.config import load_config
        from strands_bedrock_agent.logging_setup import configure_logging

        cli_overrides: dict = {}
        if args.log_level is not None:
            cli_overrides["log_level"] = args.log_level

        config = load_config(cli_overrides=cli_overrides)

        # Configure logging
        configure_logging(config.log_level, config.log_level_was_invalid)

    except ConfigError as exc:
        emit_error(exc)
        return EXIT_CONFIG
    except Exception as exc:
        emit_error(exc)
        return EXIT_CONFIG

    # ------------------------------------------------------------------
    # Build Agent
    # ------------------------------------------------------------------
    try:
        from strands_bedrock_agent.agent_factory import build_agent

        bundle = build_agent(config)
    except CredentialsError as exc:
        emit_error(exc)
        return EXIT_CREDENTIALS
    except ModelUnavailableError as exc:
        emit_error(exc)
        return EXIT_MODEL_UNAVAILABLE
    except Exception as exc:
        emit_error(exc)
        return _exit_code_for(exc)

    # ------------------------------------------------------------------
    # Single-prompt mode (R6.2, R6.7)
    # ------------------------------------------------------------------
    if args.prompt is not None:
        try:
            prompt = validate_prompt(args.prompt, config.max_prompt_length)
        except PromptValidationError as exc:
            emit_error(exc)
            return EXIT_USAGE

        try:
            result = bundle.agent(prompt)
            # Extract the response text from the agent result
            response_text = _extract_response(result)
            sys.stdout.write(response_text + "\n")
            sys.stdout.flush()
            return EXIT_OK
        except Exception as exc:
            emit_error(exc)
            return _exit_code_for(exc)

    # ------------------------------------------------------------------
    # Interactive REPL mode (R6.4, R6.6, R6.8)
    # ------------------------------------------------------------------
    return _run_repl(bundle, config)


def _extract_response(result) -> str:
    """Extract the response text from an Agent invocation result."""
    if isinstance(result, str):
        return result
    # Strands Agent returns a dict-like result with various attributes
    if hasattr(result, "message"):
        msg = result.message
        if isinstance(msg, str):
            return msg
        # message might be a dict with 'content' key
        if isinstance(msg, dict):
            content = msg.get("content", [])
            if isinstance(content, list):
                texts = []
                for block in content:
                    if isinstance(block, dict) and block.get("text"):
                        texts.append(block["text"])
                return "\n".join(texts) if texts else str(msg)
            return str(content)
    if hasattr(result, "content"):
        content = result.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("text"):
                    texts.append(block["text"])
            return "\n".join(texts) if texts else str(content)
    # Fallback: convert to string
    return str(result)


def _run_repl(bundle, config) -> int:
    """Run the interactive REPL loop.

    Reads one prompt per line from stdin. Treats 'exit', 'quit', and EOF
    as exit signals. On Agent exception, prints sanitised error to stderr
    and continues (R6.8).
    """
    spinner = _ProgressSpinner()

    try:
        while True:
            # Read one line from stdin
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                # EOF or Ctrl+C: exit gracefully
                sys.stdout.write("\n")
                sys.stdout.flush()
                return EXIT_OK

            # Check for exit commands
            stripped_line = line.strip().lower()
            if stripped_line in ("exit", "quit"):
                return EXIT_OK

            # Validate prompt
            try:
                prompt = validate_prompt(line, config.max_prompt_length)
            except PromptValidationError as exc:
                emit_error(exc)
                continue

            # Invoke Agent with progress spinner (R6.6)
            spinner.start()
            try:
                result = bundle.agent(prompt)
                spinner.stop()
                response_text = _extract_response(result)
                sys.stdout.write(response_text + "\n")
                sys.stdout.flush()
            except Exception as exc:
                spinner.stop()
                emit_error(exc)
                # Continue the REPL (R6.8)
                continue

    except Exception as exc:
        # R6.9: If we cannot write to stderr, exit non-zero
        try:
            emit_error(exc)
        except Exception:
            pass
        return EXIT_AGENT_ERROR
    finally:
        # Clean up the bundle
        try:
            bundle.__exit__(None, None, None)
        except Exception:
            pass
