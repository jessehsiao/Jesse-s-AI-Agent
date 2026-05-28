"""Property-based tests for MCP soft-fail invariant (Property 5).

Feature: strands-bedrock-agent, Property 5: MCP soft-fail invariant

Validates: Requirements 5.5
"""

from __future__ import annotations

import io
from unittest.mock import patch, MagicMock

from hypothesis import given, settings
from hypothesis.strategies import sampled_from

from strands_bedrock_agent.mcp_loader import MCPServerSpec, load_mcp_tools


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Exception classes that can be raised during MCPClient construction
_EXCEPTION_CLASSES = sampled_from([
    TimeoutError,
    ConnectionRefusedError,
    RuntimeError,
    ValueError,
    Exception,
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(name: str = "test-mcp-server") -> MCPServerSpec:
    """Create a test MCPServerSpec."""
    return MCPServerSpec(
        name=name,
        url="https://test-mcp.example.com",
        transport="http",
        disabled=False,
    )


# ---------------------------------------------------------------------------
# Property 5: MCP soft-fail invariant
# ---------------------------------------------------------------------------


class TestMCPSoftFailInvariant:
    """Feature: strands-bedrock-agent, Property 5: MCP soft-fail invariant"""

    @given(exc_class=_EXCEPTION_CLASSES)
    @settings(max_examples=100)
    def test_soft_fail_returns_empty_clients_records_failure_writes_warning(
        self, exc_class: type
    ):
        """Feature: strands-bedrock-agent, Property 5: MCP soft-fail invariant

        For any exception class E in {TimeoutError, ConnectionRefusedError,
        RuntimeError, ValueError, Exception} raised during MCPClient
        construction, load_mcp_tools returns a result whose clients == []
        for the failed server, whose failures names the failed server and the
        underlying error, and exactly one human-readable warning line was
        written to the operator stream.

        Validates: Requirements 5.5
        """
        spec = _make_spec("failing-server")
        operator_stream = io.StringIO()

        # Patch MCPClient constructor to raise
        with patch(
            "strands_bedrock_agent.mcp_loader.MCPClient",
            side_effect=exc_class("simulated failure"),
        ):
            result = load_mcp_tools(
                specs=[spec],
                connect_timeout_seconds=10,
                operator_stream=operator_stream,
            )

        # Property assertions:

        # 1. clients == [] for the failed server
        assert result.clients == [], (
            f"Expected empty clients list, got {result.clients}"
        )

        # 2. failures names the failed server and the underlying error
        assert len(result.failures) == 1, (
            f"Expected exactly one failure, got {len(result.failures)}"
        )
        failed_server_name, error_message = result.failures[0]
        assert failed_server_name == "failing-server", (
            f"Expected failure for 'failing-server', got '{failed_server_name}'"
        )
        assert exc_class.__name__ in error_message, (
            f"Expected error message to contain '{exc_class.__name__}', "
            f"got '{error_message}'"
        )

        # 3. Exactly one human-readable warning line was written to operator_stream
        output = operator_stream.getvalue()
        lines = [line for line in output.split("\n") if line.strip()]
        assert len(lines) == 1, (
            f"Expected exactly one warning line, got {len(lines)}: {lines!r}"
        )
        # The line should mention the server name
        assert "failing-server" in lines[0], (
            f"Expected warning line to mention 'failing-server', got: {lines[0]!r}"
        )

    def test_successful_construction_returns_client(self):
        """When MCPClient construction succeeds, the client is in the result."""
        spec = _make_spec("good-server")
        operator_stream = io.StringIO()

        mock_client = MagicMock()

        with patch(
            "strands_bedrock_agent.mcp_loader.MCPClient",
            return_value=mock_client,
        ):
            result = load_mcp_tools(
                specs=[spec],
                connect_timeout_seconds=10,
                operator_stream=operator_stream,
            )

        assert len(result.clients) == 1
        assert result.clients[0] is mock_client
        assert result.failures == []
        assert operator_stream.getvalue() == ""
