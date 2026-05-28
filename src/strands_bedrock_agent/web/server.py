"""FastAPI web backend for strands-bedrock-agent.

Serves the Web Chat UI at ``/`` and exposes ``POST /api/chat`` for
browser-based interaction with the Agent. Built once at startup; the
Agent and MCP clients live in ``app.state`` for the process lifetime.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.10, 9.11, 9.12
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from strands_bedrock_agent.agent_factory import (
    AgentBundle,
    build_agent,
    get_recorded_invocations,
)
from strands_bedrock_agent.cli import validate_prompt
from strands_bedrock_agent.config import (
    DEFAULT_WEB_HOST,
    DEFAULT_WEB_PORT,
    load_config,
)
from strands_bedrock_agent.errors import (
    ERROR_CLASS_CATEGORY,
    EXIT_USAGE,
    PortValidationError,
    PromptValidationError,
    render_error,
)
from strands_bedrock_agent.logging_setup import (
    EVENT_AGENT_ERROR,
    EVENT_BEDROCK_INVOKE_END,
    EVENT_BEDROCK_INVOKE_START,
    configure_logging,
    log_event,
)

from .schemas import ChatRequest, ChatResponse, ErrorResponse, ToolInvocation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _THIS_DIR / "static"
_INDEX_HTML = _STATIC_DIR / "index.html"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load config, build agent, store on app.state.

    Shutdown: exit the AgentBundle to close MCP clients.
    """
    config = load_config()
    configure_logging(config.log_level, config.log_level_was_invalid)
    bundle = build_agent(config)
    app.state.bundle = bundle
    app.state.config = config
    try:
        yield
    finally:
        bundle.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan, title="strands-bedrock-agent")

# Mount static files — create directory if it doesn't exist so the mount
# doesn't fail during import (the actual files are added in task 9.x).
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Response extraction helper
# ---------------------------------------------------------------------------


def _extract_response(result: Any) -> str:
    """Extract the response text from an Agent invocation result.

    Handles various Strands Agent result shapes:
    - Plain string
    - Object with .message attribute (str or dict with content blocks)
    - Object with .content attribute
    """
    if isinstance(result, str):
        return result
    if hasattr(result, "message"):
        msg = result.message
        if isinstance(msg, str):
            return msg
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
    return str(result)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    """Serve the Web Chat UI single-page HTML."""
    return FileResponse(str(_INDEX_HTML))


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def chat(request: Request) -> Any:
    """Process a chat prompt through the Agent.

    Validates the request body, invokes the Agent with a timeout, and
    returns the response with tool invocation metadata.

    Flow:
      1. Validate Content-Type (R9.8).
      2. Parse JSON body and validate via Pydantic (R9.8).
      3. Defence-in-depth: validate_prompt post-Pydantic.
      4. Drain pre-existing recorded invocations (thread-local).
      5. Invoke Agent with asyncio.wait_for timeout (R9.10, R9.11).
      6. On success: drain invocations, return ChatResponse.
      7. On timeout/error: classify and return HTTP 500 (R9.11).
      8. Emit structured logs for every request (R9.12).
    """
    bundle: AgentBundle = request.app.state.bundle
    config = request.app.state.config
    start_time = time.time()

    # --- Content-Type validation (R9.8) ---
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return JSONResponse(
            status_code=400,
            content={"error": "Content-Type must be application/json"},
        )

    # --- Parse and validate body via Pydantic (R9.8) ---
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body"},
        )

    try:
        chat_req = ChatRequest(**body)
    except Exception as exc:
        # Pydantic validation error
        return JSONResponse(
            status_code=400,
            content={"error": str(exc)},
        )

    prompt = chat_req.prompt

    # --- Defence-in-depth: validate_prompt post-Pydantic (R9.8) ---
    try:
        prompt = validate_prompt(prompt, config.max_prompt_length)
    except PromptValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": str(exc)},
        )

    # --- Structured log: request received (R9.12) ---
    log_event(
        logger,
        logging.INFO,
        EVENT_BEDROCK_INVOKE_START,
        model_id=config.bedrock_model_id,
        region=config.aws_region,
        prompt=prompt,
    )

    # --- Drain any pre-existing recorded invocations (thread-local) ---
    get_recorded_invocations(bundle)

    # --- Invoke the Agent with timeout (R9.10, R9.11) ---
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(bundle.agent, prompt),
            timeout=config.web_request_timeout,
        )
    except asyncio.TimeoutError:
        elapsed_ms = int((time.time() - start_time) * 1000)
        error_msg = (
            f"timeout: request exceeded {config.web_request_timeout}s limit"
        )
        log_event(
            logger,
            logging.ERROR,
            EVENT_AGENT_ERROR,
            category="timeout",
            message=error_msg,
            latency_ms=elapsed_ms,
        )
        return JSONResponse(
            status_code=500,
            content={"error": error_msg},
        )
    except Exception as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        # Classify the exception into a category (bedrock/mcp/unhandled)
        category = ERROR_CLASS_CATEGORY.get(type(exc), "unhandled")
        message = str(exc)
        sanitised = render_error(category, message)
        log_event(
            logger,
            logging.ERROR,
            EVENT_AGENT_ERROR,
            category=category,
            message=message,
            latency_ms=elapsed_ms,
        )
        return JSONResponse(
            status_code=500,
            content={"error": sanitised},
        )

    # --- Success path ---
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Extract response text from the Agent result
    response_text = _extract_response(result)

    # Drain recorded tool invocations
    raw_invocations = get_recorded_invocations(bundle)
    tool_invocations = [
        ToolInvocation(
            tool_name=inv.tool_name,
            started_at=inv.started_at,
            completed_at=inv.completed_at,
        )
        for inv in raw_invocations
    ]

    # Structured log: request completed (R9.12)
    log_event(
        logger,
        logging.INFO,
        EVENT_BEDROCK_INVOKE_END,
        model_id=config.bedrock_model_id,
        latency_ms=elapsed_ms,
        output_bytes=len(response_text.encode("utf-8")),
        tool_count=len(tool_invocations),
    )

    return ChatResponse(
        response=response_text,
        tool_invocations=tool_invocations,
    )


# ---------------------------------------------------------------------------
# Port validation (Property 11)
# ---------------------------------------------------------------------------


def validate_port(p: Any) -> int:
    """Validate and return *p* as an integer port in [1024, 65535].

    Raises:
        PortValidationError: if *p* cannot be converted to int or is outside
            the accepted range. The error message contains the offending
            value/type and the literal string ``"1024-65535"``.
    """
    try:
        port = int(p)
    except (ValueError, TypeError):
        raise PortValidationError(
            f"Invalid port value {p!r} (type={type(p).__name__}): "
            f"must be an integer in range 1024-65535"
        )
    if not (1024 <= port <= 65535):
        raise PortValidationError(
            f"Port {port} is out of range: must be in range 1024-65535"
        )
    return port


# ---------------------------------------------------------------------------
# CLI entry point: main()
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Console script ``strands-bedrock-agent-web`` entry point.

    Parses ``--port``, ``--host``, and ``--allow-non-loopback``, validates
    the port range, performs a pre-bind probe, prints the listening URL to
    stdout, and starts uvicorn.

    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
    """
    import uvicorn

    parser = argparse.ArgumentParser(
        prog="strands-bedrock-agent-web",
        description="Start the strands-bedrock-agent web server.",
    )
    parser.add_argument(
        "--port",
        default=os.environ.get("WEB_PORT", str(DEFAULT_WEB_PORT)),
        help=(
            f"Port to listen on (default: WEB_PORT env or {DEFAULT_WEB_PORT}). "
            "Must be in range 1024-65535."
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_WEB_HOST,
        help=f"Host to bind to (default: {DEFAULT_WEB_HOST}).",
    )
    parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        default=False,
        help="Allow binding to hosts other than 127.0.0.1.",
    )

    args = parser.parse_args(argv)

    # --- Validate port (R9.4) ---
    try:
        port = validate_port(args.port)
    except PortValidationError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    host: str = args.host

    # --- Refuse non-loopback unless explicitly allowed (R9.5) ---
    if host != "127.0.0.1" and not args.allow_non_loopback:
        print(
            f"Refusing to bind to non-loopback host '{host}'. "
            "Pass --allow-non-loopback to override.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    # --- Pre-bind probe: check port availability (R9.4) ---
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, port))
        probe.close()
    except OSError as exc:
        print(
            f"Cannot bind to {host}:{port}: {exc}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    # --- Print listening line to stdout (R9.2) ---
    print(f"Listening on http://{host}:{port}")

    # --- Start uvicorn ---
    uvicorn.run(
        "strands_bedrock_agent.web.server:app",
        host=host,
        port=port,
        log_config=None,
    )

    return 0
