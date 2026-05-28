# Implementation Plan: Stdio MCP Transport

## Overview

This implementation extends the existing `mcp_loader.py` to support stdio-based MCP servers alongside the current streamable-HTTP transport. The work is structured as incremental steps: first extending the data model, then parsing/validation, then client construction, then tests, and finally documentation. Each step builds on the previous and integrates immediately into the existing codebase.

## Tasks

- [x] 1. Extend MCPServerSpec dataclass with stdio fields
  - [x] 1.1 Add optional stdio fields to MCPServerSpec
    - Modify `src/strands_bedrock_agent/mcp_loader.py`
    - Add `command: str = ""` field for the stdio executable
    - Add `args: tuple[str, ...] = ()` field for command-line arguments
    - Add `env: dict[str, str] = field(default_factory=dict)` field for environment variables
    - Change `url` field to have a default of `""` (no longer always required)
    - Keep `frozen=True` on the dataclass
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2_

- [x] 2. Extend parse_mcp_config to validate stdio entries
  - [x] 2.1 Implement stdio entry parsing and validation in parse_mcp_config
    - Modify `src/strands_bedrock_agent/mcp_loader.py`
    - Add branch for `"type": "stdio"` that extracts `command`, `args`, `env` fields
    - Validate `command` is a non-whitespace string between 1-1024 chars after trim
    - Validate `args` is an array of strings, max 64 elements, each max 4096 chars
    - Validate `env` is an object of string key-value pairs, max 64 entries, keys max 256 chars, values max 8192 chars
    - Silently ignore `url` field on stdio entries
    - Raise `ConfigError` with server name and descriptive message for each violation
    - Handle `disabled: true` entries (validate then skip)
    - Add branch for unrecognized transport types (not "http", "stdio", or "sse") raising ConfigError
    - Update existing "sse" rejection to include server name in error message
    - Preserve declaration order of entries in the returned list
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8, 1.9, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 2.2 Write property test for valid stdio configuration round-trip
    - **Property 1: Valid stdio configuration round-trip**
    - Create `tests/test_stdio_property1.py`
    - Use Hypothesis to generate random valid command (1-1024 non-whitespace chars), args (0-64 strings each ≤4096 chars), env (0-64 entries, keys 1-256 chars, values 0-8192 chars)
    - Write to temp mcp.json, call `parse_mcp_config`, verify MCPServerSpec fields match input exactly
    - Verify defaults: absent args → empty tuple, absent env → empty dict
    - **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2**

  - [ ]* 2.3 Write property test for invalid stdio configuration rejection
    - **Property 2: Invalid stdio configuration rejection**
    - Create `tests/test_stdio_property2.py`
    - Use Hypothesis to generate invalid configurations: missing command, whitespace-only command, command >1024 chars, args not array, args with non-string elements, args >64 elements, args element >4096 chars, env not object, env with non-string keys/values, env >64 entries, env key >256 chars, env value >8192 chars
    - Verify `ConfigError` is raised and message contains the server entry key name
    - **Validates: Requirements 1.5, 1.8, 2.3, 2.4**

  - [ ]* 2.4 Write property test for unrecognized transport type rejection
    - **Property 3: Unrecognized transport type rejection**
    - Create `tests/test_stdio_property3.py`
    - Use Hypothesis to generate random type strings ∉ {"http", "stdio", "sse"}
    - Verify `ConfigError` is raised and message contains the server entry key name and the unrecognized type
    - **Validates: Requirements 1.9, 2.7**

- [x] 3. Checkpoint - Ensure parsing tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Extend load_mcp_tools to construct stdio MCPClients
  - [x] 4.1 Implement stdio transport dispatch in load_mcp_tools
    - Modify `src/strands_bedrock_agent/mcp_loader.py`
    - Add import for `from mcp.client.stdio import stdio_client`
    - Add transport-dispatch branch: if `spec.transport == "stdio"`, construct MCPClient with `lambda: stdio_client(command=spec.command, args=list(spec.args), env=spec.env)`
    - Keep existing HTTP branch unchanged for `spec.transport == "http"`
    - On failure during `list_tools_sync()`, call `client.stop()` before recording failure (prevent orphaned child process)
    - Apply same soft-fail pattern: log WARNING, write operator message, record failure, continue
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 4.2 Write property test for stdio soft-fail invariant
    - **Property 4: Stdio soft-fail invariant**
    - Create `tests/test_stdio_property4.py`
    - Use Hypothesis to generate random exception classes (FileNotFoundError, PermissionError, OSError, TimeoutError, RuntimeError, Exception) × failure steps (start, list_tools_sync)
    - Mock MCPClient, verify: no exception propagated, exactly one failure tuple recorded with format `"{ExceptionType}: {message}"`, one warning line written to operator stream containing server name, failed client not in `MCPLoadResult.clients`
    - For `list_tools_sync` failures, verify `client.stop()` is called before recording failure
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 3.5, 3.6**

  - [ ]* 4.3 Write property test for declaration order preservation
    - **Property 5: Declaration order preservation**
    - Create `tests/test_stdio_property5.py`
    - Use Hypothesis to generate random sequences of HTTP and stdio specs (2-8 entries)
    - Write to temp mcp.json, call `parse_mcp_config`, verify output order matches input key order
    - Mock `load_mcp_tools` connections, verify tools are appended in declaration order
    - **Validates: Requirements 2.6, 3.4**

- [x] 5. Checkpoint - Ensure load_mcp_tools tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Unit tests and cleanup completeness
  - [x] 6.1 Write unit tests for stdio parsing and loading
    - Create `tests/test_stdio_unit.py`
    - Test: stdio entry with url field is silently ignored
    - Test: disabled stdio entry is skipped from parse output
    - Test: "sse" type raises ConfigError with server name
    - Test: unrecognized type raises ConfigError with server name and type value
    - Test: stdio client construction uses stdio_client transport factory (mock MCPClient)
    - Test: list_tools_sync failure calls client.stop() before recording failure
    - Test: all servers fail returns empty MCPLoadResult (empty tools, empty clients, all failures recorded)
    - Test: mixed HTTP and stdio tools are combined in MCPLoadResult.tools
    - Test: AgentBundle.__exit__ continues after one client.stop() raises
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.9, 2.5, 3.1, 3.3, 3.6, 4.1, 4.2, 4.5, 5.1, 5.4, 5.5_

  - [ ]* 6.2 Write property test for cleanup completeness
    - **Property 6: Cleanup completeness**
    - Create `tests/test_stdio_property6.py`
    - Use Hypothesis to generate random lists of mock MCPClient instances (1-10 clients) where a random subset raise exceptions on `stop()`
    - Construct AgentBundle with those clients, call `__exit__`, verify `stop()` was called on every client regardless of exceptions
    - **Validates: Requirements 5.1, 5.4, 5.5**

- [x] 7. Create test fixture echo MCP server
  - [x] 7.1 Create echo MCP server fixture for integration testing
    - Create `tests/fixtures/echo_mcp_server.py`
    - Implement a minimal MCP server over stdio that exposes a single `echo` tool
    - The echo tool accepts a `message` string parameter and returns it unchanged
    - Use the `mcp` library's server-side API to implement the protocol
    - Ensure the script is executable and can be invoked as `python tests/fixtures/echo_mcp_server.py`
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 7.2 Write integration tests using the echo fixture
    - Create `tests/test_stdio_integration.py`
    - Test: spawn echo_mcp_server.py via stdio transport, verify tools are loaded successfully
    - Test: use a nonexistent command, verify soft-fail behavior (no exception, failure recorded)
    - _Requirements: 3.1, 3.2, 4.1, 4.5_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Update README documentation
  - [x] 9.1 Add stdio MCP server documentation to README.md
    - Modify `README.md`
    - Document the stdio server configuration schema: `"type": "stdio"`, required `"command"` field, optional `"args"` array, optional `"env"` object, optional `"disabled"` boolean
    - Provide a complete example entry in a fenced JSON code block showing all fields
    - Provide an end-to-end `mcp.json` example with both HTTP and stdio entries
    - Document lifecycle behavior: child processes spawned at startup, terminated gracefully on shutdown, forcefully killed after 5 seconds
    - Document soft-fail behavior: failed stdio server doesn't prevent startup, remaining tools still loaded, WARNING log with server name and error
    - Document at least three failure scenarios: command not found, permission denied, server crashes after startup
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python (matching the existing codebase and design document)
- The existing `AgentBundle.__exit__` already handles stdio client cleanup via `client.stop()` — no modification needed there
- The `mcp.client.stdio.stdio_client` import is the key new dependency for stdio transport

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "6.1"] },
    { "id": 5, "tasks": ["6.2", "7.1"] },
    { "id": 6, "tasks": ["7.2"] },
    { "id": 7, "tasks": ["9.1"] }
  ]
}
```
