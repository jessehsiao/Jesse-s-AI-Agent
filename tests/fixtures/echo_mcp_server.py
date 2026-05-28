#!/usr/bin/env python3
"""Minimal MCP server over stdio that exposes a single 'echo' tool.

This fixture is used for integration testing of the stdio MCP transport.
The echo tool accepts a ``message`` string parameter and returns it unchanged.

Usage:
    python tests/fixtures/echo_mcp_server.py
"""

from mcp.server import FastMCP

mcp = FastMCP("echo-server")


@mcp.tool()
def echo(message: str) -> str:
    """Echo the input message back unchanged.

    Args:
        message: The message string to echo back.

    Returns:
        The same message string, unchanged.
    """
    return message


if __name__ == "__main__":
    mcp.run(transport="stdio")
