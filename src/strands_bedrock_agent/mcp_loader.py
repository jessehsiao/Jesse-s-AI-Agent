"""MCP server configuration parsing and tool loading for strands-bedrock-agent.

Parses `.kiro/settings/mcp.json`, builds an MCPClient per declared server,
attempts connection within the configured timeout, and returns the joined list
of registered tools. On per-server failure: logs a WARNING, emits an
operator-visible message, and continues with zero tools from that server (R5.5).

Requirements: 5.1, 5.2, 5.3, 5.5
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Sequence

from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient

from strands_bedrock_agent.errors import ConfigError
from strands_bedrock_agent.logging_setup import EVENT_MCP_CONNECT, log_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MCPServerSpec:
    """Specification for a single MCP server declared in mcp.json."""

    name: str  # e.g., "aws-knowledge-mcp-server"
    transport: str  # "http" or "stdio"
    disabled: bool

    # HTTP-specific fields
    url: str = ""  # Required for transport="http"

    # Stdio-specific fields
    command: str = ""  # Required for transport="stdio" (1-1024 chars after trim)
    args: tuple[str, ...] = ()  # Optional, max 64 elements, each max 4096 chars
    env: dict[str, str] = field(default_factory=dict)  # Optional, max 64 entries


@dataclass
class MCPLoadResult:
    """Result of attempting to load tools from all configured MCP servers."""

    tools: list = field(default_factory=list)  # Strands-compatible tool wrappers
    clients: list = field(default_factory=list)  # MCPClient instances kept alive
    failures: list[tuple[str, str]] = field(default_factory=list)  # [(server_name, error_message)]


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


def parse_mcp_config(path: Path) -> list[MCPServerSpec]:
    """Parse the MCP configuration file at *path*.

    Expected format::

        {
          "mcpServers": {
            "<server-name>": {
              "url": "<endpoint-url>",
              "type": "http",
              "disabled": false
            }
          }
        }

    Supports:
      - "type": "http" — requires "url" field (existing behavior)
      - "type": "stdio" — requires "command" field, optional "args" and "env"
      - "type": "sse" — raises ConfigError (unsupported)
      - Any other type — raises ConfigError (unrecognized)

    Validation for stdio entries:
      - "command": non-whitespace string, 1-1024 chars after trim
      - "args": array of strings, max 64 elements, each max 4096 chars
      - "env": object of string key-value pairs, max 64 entries,
               keys max 256 chars, values max 8192 chars
      - "url" field is silently ignored for stdio entries
      - "disabled": true skips the entry (after validation)

    Size limits are enforced even for disabled entries to catch config errors early.

    Args:
        path: Path to the mcp.json configuration file.

    Returns:
        A list of MCPServerSpec for all enabled servers.

    Raises:
        ConfigError: If the file is missing, contains invalid JSON, or any
            entry fails validation.
    """
    # File must exist
    if not path.is_file():
        raise ConfigError(
            "mcp_config",
            checked=(f"file:{path}",),
        )

    # Parse JSON
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(
            "mcp_config",
            checked=(f"file:{path}",),
        ) from exc

    # Validate top-level structure
    if not isinstance(data, dict):
        raise ConfigError(
            "mcp_config",
            checked=(f"file:{path}",),
        )

    servers_map = data.get("mcpServers")
    if not isinstance(servers_map, dict):
        raise ConfigError(
            "mcp_config",
            checked=(f"file:{path}",),
        )

    specs: list[MCPServerSpec] = []

    for server_name, server_cfg in servers_map.items():
        if not isinstance(server_cfg, dict):
            raise ConfigError(
                "mcp_config",
                checked=(f"file:{path}",),
            )

        transport_type = server_cfg.get("type", "")

        # --- SSE: unsupported ---
        if transport_type == "sse":
            raise ConfigError(
                f"Server '{server_name}': SSE transport is unsupported",
            )

        # --- Unrecognized transport type ---
        if transport_type not in ("http", "stdio"):
            raise ConfigError(
                f"Server '{server_name}': unrecognized transport type '{transport_type}'",
            )

        # --- HTTP transport ---
        if transport_type == "http":
            disabled = bool(server_cfg.get("disabled", False))
            if disabled:
                continue

            # Require url
            url = server_cfg.get("url")
            if not url or not isinstance(url, str):
                raise ConfigError(
                    "mcp_config",
                    checked=(f"file:{path}",),
                )

            specs.append(
                MCPServerSpec(
                    name=server_name,
                    transport="http",
                    disabled=False,
                    url=url,
                )
            )

        # --- Stdio transport ---
        elif transport_type == "stdio":
            # Validate command (enforced even for disabled entries)
            command = server_cfg.get("command")
            if (
                not isinstance(command, str)
                or not command.strip()
                or len(command.strip()) > 1024
            ):
                raise ConfigError(
                    f"Server '{server_name}': 'command' must be a non-whitespace "
                    f"string between 1 and 1024 characters for stdio transport",
                )

            command = command.strip()

            # Validate args (enforced even for disabled entries)
            args_raw = server_cfg.get("args")
            if args_raw is None:
                args_tuple: tuple[str, ...] = ()
            else:
                if not isinstance(args_raw, list):
                    raise ConfigError(
                        f"Server '{server_name}': 'args' must be an array of strings",
                    )
                if not all(isinstance(a, str) for a in args_raw):
                    raise ConfigError(
                        f"Server '{server_name}': 'args' must be an array of strings",
                    )
                if len(args_raw) > 64:
                    raise ConfigError(
                        f"Server '{server_name}': 'args' exceeds maximum of 64 elements",
                    )
                for element in args_raw:
                    if len(element) > 4096:
                        raise ConfigError(
                            f"Server '{server_name}': 'args' element exceeds maximum of 4096 characters",
                        )
                args_tuple = tuple(args_raw)

            # Validate env (enforced even for disabled entries)
            env_raw = server_cfg.get("env")
            if env_raw is None:
                env_dict: dict[str, str] = {}
            else:
                if not isinstance(env_raw, dict):
                    raise ConfigError(
                        f"Server '{server_name}': 'env' must be an object of string key-value pairs",
                    )
                if not all(
                    isinstance(k, str) and isinstance(v, str)
                    for k, v in env_raw.items()
                ):
                    raise ConfigError(
                        f"Server '{server_name}': 'env' must be an object of string key-value pairs",
                    )
                if len(env_raw) > 64:
                    raise ConfigError(
                        f"Server '{server_name}': 'env' exceeds maximum of 64 entries",
                    )
                for key, value in env_raw.items():
                    if len(key) > 256:
                        raise ConfigError(
                            f"Server '{server_name}': 'env' key exceeds maximum of 256 characters",
                        )
                    if len(value) > 8192:
                        raise ConfigError(
                            f"Server '{server_name}': 'env' value exceeds maximum of 8192 characters",
                        )
                env_dict = dict(env_raw)

            # Check disabled flag — validate then skip
            disabled = bool(server_cfg.get("disabled", False))
            if disabled:
                continue

            specs.append(
                MCPServerSpec(
                    name=server_name,
                    transport="stdio",
                    disabled=False,
                    command=command,
                    args=args_tuple,
                    env=env_dict,
                )
            )

    return specs


# ---------------------------------------------------------------------------
# Tool loading
# ---------------------------------------------------------------------------


def load_mcp_tools(
    specs: Sequence[MCPServerSpec],
    connect_timeout_seconds: int,
    operator_stream: IO[str] | None = None,
) -> MCPLoadResult:
    """Construct MCPClient instances for each configured MCP server.

    For each enabled spec:
      - HTTP: Build an MCPClient with streamable-HTTP transport factory.
      - Stdio: Build an MCPClient with stdio_client transport factory.

    The clients are NOT started here. The Strands Agent SDK manages the
    MCPClient lifecycle via the ToolProvider interface — it calls start()
    and load_tools() internally when the Agent is constructed. Starting
    clients here would cause a "session already running" error when the
    Agent later invokes load_tools() → start().

    On per-server failure during construction:
      - Emit an EVENT_MCP_CONNECT WARNING log with the server name and error.
      - Write one operator-visible line to *operator_stream*.
      - Record the failure in ``MCPLoadResult.failures``.
      - Continue with that server contributing zero tools.

    This function MUST NOT raise on construction failure (soft-fail per R5.5).

    Args:
        specs: Sequence of MCPServerSpec to build clients for.
        connect_timeout_seconds: Maximum seconds to wait for each server
            connection (used as context for logging; actual timeout is
            handled by the transport layer at start time).
        operator_stream: Writable text stream for operator-visible messages
            (typically sys.stderr). If None, operator messages are suppressed.

    Returns:
        MCPLoadResult with constructed clients and any per-server failures.
    """
    result = MCPLoadResult()

    for spec in specs:
        if spec.disabled:
            continue

        if spec.transport == "stdio":
            _load_stdio_server(spec, connect_timeout_seconds, operator_stream, result)
        else:
            _load_http_server(spec, connect_timeout_seconds, operator_stream, result)

    return result


def _load_http_server(
    spec: MCPServerSpec,
    connect_timeout_seconds: int,
    operator_stream: IO[str] | None,
    result: MCPLoadResult,
) -> None:
    """Construct an MCPClient for an HTTP MCP server.

    The client is NOT started here. The Strands Agent SDK manages the
    MCPClient lifecycle via the ToolProvider interface — calling start()
    and load_tools() internally when the Agent is constructed. Starting
    the client here would cause a "session already running" error when
    the Agent later calls load_tools() → start().
    """
    try:
        client = MCPClient(lambda url=spec.url: streamablehttp_client(url=url))
        result.clients.append(client)

    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"

        log_event(
            logger,
            logging.WARNING,
            EVENT_MCP_CONNECT,
            server_name=spec.name,
            endpoint=spec.url,
            error=error_message,
            timeout_seconds=connect_timeout_seconds,
        )

        if operator_stream is not None:
            operator_stream.write(
                f"AWS documentation tools unavailable for this session: {spec.name}\n"
            )

        result.failures.append((spec.name, error_message))


def _load_stdio_server(
    spec: MCPServerSpec,
    connect_timeout_seconds: int,
    operator_stream: IO[str] | None,
    result: MCPLoadResult,
) -> None:
    """Construct an MCPClient for a stdio MCP server.

    The client is NOT started here. The Strands Agent SDK manages the
    MCPClient lifecycle via the ToolProvider interface — calling start()
    and load_tools() internally when the Agent is constructed. Starting
    the client here would cause a "session already running" error when
    the Agent later calls load_tools() → start().
    """
    try:
        client = MCPClient(
            lambda cmd=spec.command, args=list(spec.args), env=spec.env: stdio_client(
                server=StdioServerParameters(command=cmd, args=args, env=env)
            )
        )
        result.clients.append(client)

    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"

        log_event(
            logger,
            logging.WARNING,
            EVENT_MCP_CONNECT,
            server_name=spec.name,
            command=spec.command,
            error=error_message,
            timeout_seconds=connect_timeout_seconds,
        )

        if operator_stream is not None:
            operator_stream.write(
                f"MCP tools unavailable for this session: {spec.name}\n"
            )

        result.failures.append((spec.name, error_message))
