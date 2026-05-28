"""Example-based unit tests for stdio MCP transport support.

Covers:
- stdio entry with url field is silently ignored
- disabled stdio entry is skipped from parse output
- "sse" type raises ConfigError with server name
- unrecognized type raises ConfigError with server name and type value
- stdio client construction uses stdio_client transport factory (mock MCPClient)
- MCPClient construction failure records failure gracefully
- all servers fail returns empty MCPLoadResult (empty clients, all failures recorded)
- mixed HTTP and stdio clients are combined in MCPLoadResult.clients
- AgentBundle.__exit__ continues after one client.stop() raises

Requirements: 1.4, 1.5, 1.6, 1.7, 1.9, 2.5, 3.1, 3.3, 3.4, 3.6, 4.1, 4.2, 4.5, 5.1, 5.4, 5.5
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from strands_bedrock_agent.agent_factory import AgentBundle
from strands_bedrock_agent.errors import ConfigError
from strands_bedrock_agent.mcp_loader import (
    MCPServerSpec,
    load_mcp_tools,
    parse_mcp_config,
)


# ---------------------------------------------------------------------------
# Tests: stdio entry with url field is silently ignored
# ---------------------------------------------------------------------------


class TestStdioUrlFieldIgnored:
    """Requirement 1.6: url field is silently ignored for stdio entries."""

    def test_stdio_entry_with_url_field_is_ignored(self, tmp_path: Path):
        """A stdio entry that includes a 'url' field parses without error,
        and the url is not carried into the MCPServerSpec."""
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "my-stdio-server": {
                    "type": "stdio",
                    "command": "python",
                    "args": ["-m", "my_server"],
                    "url": "https://should-be-ignored.example.com",
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        specs = parse_mcp_config(config_file)

        assert len(specs) == 1
        assert specs[0].name == "my-stdio-server"
        assert specs[0].transport == "stdio"
        assert specs[0].command == "python"
        assert specs[0].args == ("-m", "my_server")
        # url field should be the default empty string (ignored)
        assert specs[0].url == ""


# ---------------------------------------------------------------------------
# Tests: disabled stdio entry is skipped from parse output
# ---------------------------------------------------------------------------


class TestDisabledStdioEntrySkipped:
    """Requirement 1.7: disabled stdio entries are excluded from parse output."""

    def test_disabled_stdio_entry_not_in_results(self, tmp_path: Path):
        """A stdio entry with disabled: true is validated but not returned."""
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "disabled-stdio": {
                    "type": "stdio",
                    "command": "python",
                    "args": ["-m", "my_server"],
                    "disabled": True,
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        specs = parse_mcp_config(config_file)
        assert specs == []

    def test_disabled_stdio_mixed_with_enabled(self, tmp_path: Path):
        """Only enabled entries appear in the result list."""
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "disabled-stdio": {
                    "type": "stdio",
                    "command": "python",
                    "disabled": True,
                },
                "enabled-stdio": {
                    "type": "stdio",
                    "command": "node",
                    "args": ["server.js"],
                },
            }
        }
        config_file.write_text(json.dumps(config_data))

        specs = parse_mcp_config(config_file)
        assert len(specs) == 1
        assert specs[0].name == "enabled-stdio"
        assert specs[0].command == "node"


# ---------------------------------------------------------------------------
# Tests: "sse" type raises ConfigError with server name
# ---------------------------------------------------------------------------


class TestSseTypeRaisesConfigError:
    """Requirement 2.5: SSE transport raises ConfigError with server name."""

    def test_sse_type_raises_config_error_with_server_name(self, tmp_path: Path):
        """An entry with type 'sse' raises ConfigError whose message contains
        the server entry key name."""
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "my-sse-server": {
                    "type": "sse",
                    "url": "https://example.com/sse",
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        with pytest.raises(ConfigError) as exc_info:
            parse_mcp_config(config_file)

        # The error message should contain the server name
        error_msg = str(exc_info.value)
        assert "my-sse-server" in error_msg
        assert "SSE" in error_msg or "sse" in error_msg.lower()


# ---------------------------------------------------------------------------
# Tests: unrecognized type raises ConfigError with server name and type value
# ---------------------------------------------------------------------------


class TestUnrecognizedTypeRaisesConfigError:
    """Requirement 1.9, 2.7: unrecognized transport type raises ConfigError."""

    def test_unrecognized_type_raises_with_server_name_and_type(self, tmp_path: Path):
        """An entry with an unrecognized type raises ConfigError whose message
        contains both the server name and the unrecognized type value."""
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "weird-server": {
                    "type": "grpc",
                    "url": "https://example.com/grpc",
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        with pytest.raises(ConfigError) as exc_info:
            parse_mcp_config(config_file)

        error_msg = str(exc_info.value)
        assert "weird-server" in error_msg
        assert "grpc" in error_msg

    def test_empty_type_raises_config_error(self, tmp_path: Path):
        """An entry with an empty type string raises ConfigError."""
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "no-type-server": {
                    "type": "",
                    "url": "https://example.com",
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        with pytest.raises(ConfigError) as exc_info:
            parse_mcp_config(config_file)

        error_msg = str(exc_info.value)
        assert "no-type-server" in error_msg


# ---------------------------------------------------------------------------
# Tests: stdio client construction uses stdio_client transport factory
# ---------------------------------------------------------------------------


class TestStdioClientConstruction:
    """Requirement 3.1: stdio MCPClient uses stdio_client transport factory."""

    def test_stdio_client_uses_stdio_transport_factory(self):
        """When load_mcp_tools processes a stdio spec, it constructs MCPClient
        with a transport factory that invokes stdio_client."""
        spec = MCPServerSpec(
            name="local-server",
            transport="stdio",
            disabled=False,
            command="npx",
            args=("-y", "@modelcontextprotocol/server-filesystem", "/tmp"),
            env={"NODE_ENV": "production"},
        )

        mock_client_instance = MagicMock()

        captured_factory = None

        def capture_mcp_client(factory):
            nonlocal captured_factory
            captured_factory = factory
            return mock_client_instance

        with patch(
            "strands_bedrock_agent.mcp_loader.MCPClient",
            side_effect=capture_mcp_client,
        ), patch(
            "strands_bedrock_agent.mcp_loader.stdio_client"
        ) as mock_stdio_client:
            result = load_mcp_tools([spec], connect_timeout_seconds=10)

            # Invoke the captured factory to verify it calls stdio_client
            assert captured_factory is not None
            captured_factory()

            mock_stdio_client.assert_called_once_with(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                env={"NODE_ENV": "production"},
            )

        assert len(result.clients) == 1
        assert result.clients[0] is mock_client_instance
        assert result.failures == []
        # start() and list_tools_sync() should NOT be called —
        # the Agent SDK handles lifecycle via ToolProvider interface
        mock_client_instance.start.assert_not_called()
        mock_client_instance.list_tools_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: MCPClient construction failure records failure gracefully
# ---------------------------------------------------------------------------


class TestConstructionFailureRecordsFailure:
    """Requirement 3.6: MCPClient construction failure is recorded gracefully."""

    def test_construction_failure_records_failure(self):
        """When MCPClient() constructor raises, the failure is recorded
        in MCPLoadResult and no client is added."""
        spec = MCPServerSpec(
            name="failing-server",
            transport="stdio",
            disabled=False,
            command="python",
            args=("-m", "broken_server"),
        )

        with patch(
            "strands_bedrock_agent.mcp_loader.MCPClient",
            side_effect=RuntimeError("construction failed"),
        ):
            result = load_mcp_tools([spec], connect_timeout_seconds=10)

        # Failure should be recorded
        assert len(result.failures) == 1
        assert result.failures[0][0] == "failing-server"
        assert "RuntimeError" in result.failures[0][1]
        assert "construction failed" in result.failures[0][1]
        # No clients from the failed server
        assert result.clients == []


# ---------------------------------------------------------------------------
# Tests: all servers fail returns empty MCPLoadResult
# ---------------------------------------------------------------------------


class TestAllServersFailReturnsEmptyResult:
    """Requirement 4.5: all servers failing returns empty clients."""

    def test_all_servers_fail_returns_empty_result(self):
        """When all configured servers fail construction, MCPLoadResult has
        empty clients and all failures recorded."""
        specs = [
            MCPServerSpec(
                name="http-fail",
                transport="http",
                disabled=False,
                url="https://unreachable.example.com/mcp",
            ),
            MCPServerSpec(
                name="stdio-fail",
                transport="stdio",
                disabled=False,
                command="nonexistent-command",
            ),
        ]

        # Both clients fail on construction
        def fail_construction(*args, **kwargs):
            raise ConnectionError("construction failed")

        call_count = [0]
        errors = [
            ConnectionError("connection refused"),
            FileNotFoundError("command not found"),
        ]

        def fail_with_different_errors(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            raise errors[idx]

        with patch(
            "strands_bedrock_agent.mcp_loader.MCPClient",
            side_effect=fail_with_different_errors,
        ):
            result = load_mcp_tools(specs, connect_timeout_seconds=10)

        assert result.clients == []
        assert len(result.failures) == 2
        assert result.failures[0][0] == "http-fail"
        assert "ConnectionError" in result.failures[0][1]
        assert result.failures[1][0] == "stdio-fail"
        assert "FileNotFoundError" in result.failures[1][1]


# ---------------------------------------------------------------------------
# Tests: mixed HTTP and stdio tools are combined in MCPLoadResult.tools
# ---------------------------------------------------------------------------


class TestMixedHttpStdioToolsCombined:
    """Requirement 3.3, 3.4: clients from both transports are combined."""

    def test_mixed_http_and_stdio_clients_combined(self):
        """Clients from HTTP and stdio servers are combined in MCPLoadResult.clients
        in declaration order."""
        specs = [
            MCPServerSpec(
                name="http-server",
                transport="http",
                disabled=False,
                url="https://example.com/mcp",
            ),
            MCPServerSpec(
                name="stdio-server",
                transport="stdio",
                disabled=False,
                command="python",
                args=("-m", "my_server"),
            ),
        ]

        mock_http_client = MagicMock()
        mock_stdio_client = MagicMock()

        clients_iter = iter([mock_http_client, mock_stdio_client])

        with patch(
            "strands_bedrock_agent.mcp_loader.MCPClient",
            side_effect=lambda *args, **kwargs: next(clients_iter),
        ):
            result = load_mcp_tools(specs, connect_timeout_seconds=10)

        assert len(result.clients) == 2
        assert result.clients[0] is mock_http_client
        assert result.clients[1] is mock_stdio_client
        assert result.failures == []


# ---------------------------------------------------------------------------
# Tests: AgentBundle.__exit__ continues after one client.stop() raises
# ---------------------------------------------------------------------------


class TestAgentBundleExitContinuesAfterStopFailure:
    """Requirement 5.1, 5.4, 5.5: __exit__ continues when stop() raises."""

    def test_exit_continues_after_one_stop_raises(self):
        """AgentBundle.__exit__ calls stop() on all clients even if one raises."""
        client_a = MagicMock()
        client_a.stop.side_effect = OSError("process already dead")

        client_b = MagicMock()
        client_b.stop.return_value = None

        client_c = MagicMock()
        client_c.stop.side_effect = RuntimeError("unexpected error")

        bundle = AgentBundle(
            agent=MagicMock(),
            mcp_clients=[client_a, client_b, client_c],
        )

        # __exit__ should not raise
        bundle.__exit__(None, None, None)

        # All clients should have stop() called
        client_a.stop.assert_called_once()
        client_b.stop.assert_called_once()
        client_c.stop.assert_called_once()

    def test_exit_with_no_clients_does_not_raise(self):
        """AgentBundle.__exit__ with empty client list completes without error."""
        bundle = AgentBundle(
            agent=MagicMock(),
            mcp_clients=[],
        )

        # Should not raise
        bundle.__exit__(None, None, None)
