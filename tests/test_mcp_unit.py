"""Example-based unit tests for mcp_loader.py.

Covers:
- Malformed JSON raises ConfigError
- disabled: true server is skipped silently
- type: "stdio" raises ConfigError
- Happy path against a mock MCPClient that returns a non-empty tool list

Requirements: 5.1, 5.3
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from strands_bedrock_agent.errors import ConfigError
from strands_bedrock_agent.mcp_loader import (
    MCPServerSpec,
    load_mcp_tools,
    parse_mcp_config,
)

# ---------------------------------------------------------------------------
# Tests: Malformed JSON raises ConfigError
# ---------------------------------------------------------------------------


class TestMalformedJsonRaisesConfigError:
    """Requirement 5.1: malformed JSON in mcp.json raises ConfigError."""

    def test_invalid_json_syntax(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text("{not valid json!!!")

        with pytest.raises(ConfigError):
            parse_mcp_config(config_file)

    def test_empty_file_raises_config_error(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text("")

        with pytest.raises(ConfigError):
            parse_mcp_config(config_file)

    def test_non_dict_top_level_raises_config_error(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps([1, 2, 3]))

        with pytest.raises(ConfigError):
            parse_mcp_config(config_file)

    def test_missing_mcp_servers_key_raises_config_error(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps({"other_key": "value"}))

        with pytest.raises(ConfigError):
            parse_mcp_config(config_file)


# ---------------------------------------------------------------------------
# Tests: disabled: true server is skipped silently
# ---------------------------------------------------------------------------


class TestDisabledServerSkipped:
    """Requirement 5.1: servers with disabled: true are not included."""

    def test_disabled_server_not_in_results(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "disabled-server": {
                    "url": "https://example.com/mcp",
                    "type": "http",
                    "disabled": True,
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        specs = parse_mcp_config(config_file)
        assert specs == []

    def test_disabled_server_mixed_with_enabled(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "disabled-server": {
                    "url": "https://disabled.example.com/mcp",
                    "type": "http",
                    "disabled": True,
                },
                "enabled-server": {
                    "url": "https://enabled.example.com/mcp",
                    "type": "http",
                    "disabled": False,
                },
            }
        }
        config_file.write_text(json.dumps(config_data))

        specs = parse_mcp_config(config_file)
        assert len(specs) == 1
        assert specs[0].name == "enabled-server"
        assert specs[0].url == "https://enabled.example.com/mcp"


# ---------------------------------------------------------------------------
# Tests: Unsupported/invalid transport types raise ConfigError
# ---------------------------------------------------------------------------


class TestUnsupportedTransportRaisesConfigError:
    """Requirements 1.5, 1.9, 2.5: invalid stdio config and unsupported transports raise ConfigError."""

    def test_stdio_missing_command_raises(self, tmp_path: Path):
        """Stdio entry without a 'command' field raises ConfigError."""
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "stdio-server": {
                    "url": "https://example.com/mcp",
                    "type": "stdio",
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        with pytest.raises(ConfigError):
            parse_mcp_config(config_file)

    def test_sse_type_raises(self, tmp_path: Path):
        """SSE transport is unsupported and raises ConfigError."""
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "sse-server": {
                    "url": "https://example.com/mcp",
                    "type": "sse",
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        with pytest.raises(ConfigError):
            parse_mcp_config(config_file)


# ---------------------------------------------------------------------------
# Tests: Happy path — mock MCPClient returns tools via load_mcp_tools
# ---------------------------------------------------------------------------


class TestLoadMcpToolsHappyPath:
    """Requirement 5.1: load_mcp_tools constructs MCPClient instances."""

    def test_mock_mcp_client_constructed(self):
        """MCPClient is constructed for each enabled server spec."""
        spec = MCPServerSpec(
            name="test-server",
            url="https://test.example.com/mcp",
            transport="http",
            disabled=False,
        )

        # Mock MCPClient instance
        mock_client_instance = MagicMock()

        with patch(
            "strands_bedrock_agent.mcp_loader.MCPClient",
            return_value=mock_client_instance,
        ):
            result = load_mcp_tools([spec], connect_timeout_seconds=10)

        # Client is constructed and added to result, but NOT started
        assert len(result.clients) == 1
        assert result.clients[0] is mock_client_instance
        assert result.failures == []
        # start() and list_tools_sync() should NOT be called —
        # the Agent SDK handles lifecycle via ToolProvider interface
        mock_client_instance.start.assert_not_called()
        mock_client_instance.list_tools_sync.assert_not_called()

    def test_multiple_servers_aggregate_clients(self):
        """Clients from multiple servers are aggregated into a single list."""
        specs = [
            MCPServerSpec(
                name="server-a",
                url="https://a.example.com/mcp",
                transport="http",
                disabled=False,
            ),
            MCPServerSpec(
                name="server-b",
                url="https://b.example.com/mcp",
                transport="http",
                disabled=False,
            ),
        ]

        # Create separate mock instances for each server
        mock_client_a = MagicMock()
        mock_client_b = MagicMock()

        clients_iter = iter([mock_client_a, mock_client_b])

        with patch(
            "strands_bedrock_agent.mcp_loader.MCPClient",
            side_effect=lambda *args, **kwargs: next(clients_iter),
        ):
            result = load_mcp_tools(specs, connect_timeout_seconds=10)

        assert len(result.clients) == 2
        assert result.clients[0] is mock_client_a
        assert result.clients[1] is mock_client_b
        assert result.failures == []
