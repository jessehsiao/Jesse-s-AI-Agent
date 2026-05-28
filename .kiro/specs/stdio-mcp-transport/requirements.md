# Requirements Document

## Introduction

This feature extends the existing MCP loader module (`mcp_loader.py`) to support stdio-based MCP servers in addition to the current HTTP-only (streamable HTTP) transport. Currently, the MCP loader explicitly rejects `"stdio"` and `"sse"` transport types with a `ConfigError`. This enhancement adds support for local stdio MCP servers — child processes that communicate over stdin/stdout — so the Operator can extend the Agent with locally-running MCP tool servers.

This spec builds upon and extends Requirement 5 (AWS Knowledge MCP Server Tool Integration) from the existing `strands-bedrock-agent` spec. The existing HTTP transport, soft-fail behavior, and configuration structure remain unchanged; stdio support is additive.

## Glossary

- **Agent**: The Strands Agents SDK `Agent` instance configured in this project that accepts a user prompt, invokes the LLM, optionally calls tools, and returns a response.
- **MCP_Client**: The Strands Agents MCP client component that connects to an MCP server and exposes its tools to the Agent.
- **MCP_Loader**: The `mcp_loader.py` module responsible for parsing MCP configuration, constructing MCP clients, and loading tools.
- **Stdio_MCP_Server**: A local MCP server that runs as a child process and communicates with the MCP_Client over standard input and standard output streams using the MCP stdio transport protocol.
- **Stdio_Transport**: The MCP stdio transport adapter (`mcp.client.stdio.stdio_client`) that spawns a child process and communicates via stdin/stdout pipes.
- **HTTP_MCP_Server**: An MCP server accessed over streamable HTTP transport (the existing supported type).
- **Configuration_File**: The MCP server configuration file at `.kiro/settings/mcp.json` that declares MCP server entries.
- **MCPServerSpec**: The internal data class representing a parsed MCP server entry from the Configuration_File.
- **MCPLoadResult**: The internal data class holding loaded tools, live clients, and per-server failures.
- **Operator**: A developer or user running the Agent locally on their workstation.
- **Child_Process**: The operating system process spawned by the Stdio_Transport to run the Stdio_MCP_Server command.
- **Soft_Fail**: The behavior where a connection failure to an MCP server logs a warning and continues startup without that server's tools, rather than terminating the application (per existing R5.5).

## Requirements

### Requirement 1: Stdio Server Configuration Schema

**User Story:** As an Operator, I want to declare stdio-based MCP servers in `mcp.json` alongside HTTP servers, so that I can configure local tool servers without changing the configuration file format.

#### Acceptance Criteria

1. THE Configuration_File SHALL accept entries with `"type": "stdio"` in the `mcpServers` map, where each stdio entry contains a `"command"` field of type string with length 1 to 1024 characters specifying the executable to run.
2. WHERE a stdio entry includes an `"args"` field, THE MCP_Loader SHALL accept it as an array of strings, each between 0 and 4096 characters, with a maximum of 64 elements, and pass the array as command-line arguments to the Child_Process.
3. WHERE a stdio entry includes an `"env"` field, THE MCP_Loader SHALL accept it as an object whose keys and values are strings, each key between 1 and 256 characters and each value between 0 and 8192 characters, with a maximum of 64 entries, and pass the object as additional environment variables to the Child_Process.
4. THE Configuration_File SHALL continue to accept entries with `"type": "http"` using the existing schema (requiring a `"url"` field), and the MCP_Loader SHALL process HTTP entries identically to the current behavior.
5. IF a stdio entry is missing the `"command"` field, or the `"command"` field is not a string, or the `"command"` field after trimming leading and trailing whitespace has length 0 or exceeds 1024 characters, THEN THE MCP_Loader SHALL raise a ConfigError that names the server entry and indicates that `"command"` must be a non-whitespace string between 1 and 1024 characters for stdio transport.
6. IF a stdio entry contains a `"url"` field, THEN THE MCP_Loader SHALL ignore the `"url"` field without raising an error, since stdio servers do not use URL-based connections.
7. WHEN a stdio entry has `"disabled": true`, THE MCP_Loader SHALL skip that entry without spawning a Child_Process, consistent with the existing disabled-server behavior for HTTP entries.
8. IF a stdio entry's `"args"` array exceeds 64 elements, or any element exceeds 4096 characters, or the `"env"` object exceeds 64 entries, or any key exceeds 256 characters, or any value exceeds 8192 characters, THEN THE MCP_Loader SHALL raise a ConfigError that names the server entry and identifies which field exceeded its size limit.
9. IF an entry has a `"type"` value that is not `"http"`, `"stdio"`, or `"sse"`, THEN THE MCP_Loader SHALL raise a ConfigError that names the server entry and indicates the unsupported transport type.

### Requirement 2: Stdio Configuration Parsing and Validation

**User Story:** As an Operator, I want the MCP loader to validate my stdio server configuration at startup, so that I receive clear error messages for misconfigured entries before the Agent attempts to connect.

#### Acceptance Criteria

1. THE `parse_mcp_config` function SHALL return an MCPServerSpec with `transport="stdio"` for each entry whose `"type"` field equals `"stdio"` and whose `"disabled"` field is absent or false.
2. THE MCPServerSpec for stdio entries SHALL carry the `command` string, the `args` list (defaulting to an empty list when the `"args"` field is absent), and the `env` dictionary (defaulting to an empty dictionary when the `"env"` field is absent). All stdio entries, including those with `"disabled": true`, SHALL meet field validation requirements (valid `"command"`, valid `"args"` array if present, valid `"env"` object if present) before being accepted or skipped.
3. IF the `"args"` field is present but is not an array, or contains any element that is not a string, THEN THE MCP_Loader SHALL raise a ConfigError that includes the server entry key name and indicates that `"args"` must be an array of strings.
4. IF the `"env"` field is present but is not an object, or contains any key that is not a string, or contains any value that is not a string, THEN THE MCP_Loader SHALL raise a ConfigError that includes the server entry key name and indicates that `"env"` must be an object of string key-value pairs.
5. IF an entry has `"type": "sse"`, THEN THE MCP_Loader SHALL raise a ConfigError that includes the server entry key name and indicates that SSE transport is unsupported.
6. WHEN the Configuration_File contains a mix of HTTP and stdio entries, THE `parse_mcp_config` function SHALL return MCPServerSpec instances for all enabled entries regardless of transport type, preserving the declaration order of keys from the `mcpServers` object.
7. IF an entry has a `"type"` value that is not one of `"http"`, `"stdio"`, or `"sse"`, THEN THE MCP_Loader SHALL raise a ConfigError that includes the server entry key name and indicates the unrecognized transport type.

### Requirement 3: Stdio MCP Client Construction and Tool Loading

**User Story:** As an Operator, I want the MCP loader to spawn stdio MCP servers and load their tools at startup, so that the Agent can use locally-provided tools alongside remote HTTP-based tools.

#### Acceptance Criteria

1. WHEN the `load_mcp_tools` function processes an MCPServerSpec with `transport="stdio"`, THE MCP_Loader SHALL construct an MCPClient using a transport factory that invokes `stdio_client(command=spec.command, args=spec.args, env=spec.env)` from the `mcp.client.stdio` module.
2. WHEN the MCPClient for a stdio server is started, THE MCP_Loader SHALL call `client.start()` to spawn the Child_Process and establish the stdio communication channel, then call `client.list_tools_sync()` to retrieve the server's available tools, applying the same `connect_timeout_seconds` constraint used for HTTP servers.
3. THE MCP_Loader SHALL append all tools retrieved from stdio servers to `MCPLoadResult.tools` and store the live MCPClient instance in `MCPLoadResult.clients`, using the same data structures and registration pattern as tools from HTTP servers, such that the Agent can invoke stdio-provided tools identically to HTTP-provided tools.
4. WHEN both HTTP and stdio servers are configured, THE MCP_Loader SHALL attempt to connect to all enabled servers in their declaration order from the Configuration_File and return the combined tool list from all successfully connected servers, preserving that declaration order.
5. IF the `command` specified in a stdio entry does not exist on the system PATH or is not executable, THEN THE MCP_Loader SHALL treat this as a connection failure and apply the Soft_Fail behavior defined in Requirement 4.
6. IF `client.start()` succeeds but `client.list_tools_sync()` raises an exception, THEN THE MCP_Loader SHALL call `client.stop()` on the partially-started MCPClient before recording the failure, to prevent an orphaned Child_Process.

### Requirement 4: Stdio Server Soft-Fail Behavior

**User Story:** As an Operator, I want stdio server failures to be handled gracefully, so that a misconfigured or unavailable local MCP server does not prevent the Agent from starting with its remaining tools.

#### Acceptance Criteria

1. IF the MCPClient for a stdio server raises any exception during `start()` (including `FileNotFoundError`, `PermissionError`, `OSError`, `TimeoutError`, or any subclass of `Exception`), THEN THE MCP_Loader SHALL log a WARNING-level structured log record containing the server name, the command that failed, and the error message formatted as `"{ExceptionType}: {message}"`, write one line to the operator stream indicating that tools from that server are unavailable, record the failure in `MCPLoadResult.failures`, and continue processing remaining servers without adding the failed client to `MCPLoadResult.clients`.
2. IF the MCPClient for a stdio server raises any exception during `list_tools_sync()`, THEN THE MCP_Loader SHALL stop the already-started MCPClient to terminate the Child_Process, then apply the same logging, operator notification, and failure-recording behavior as criterion 1, with the failed server contributing zero tools.
3. THE `load_mcp_tools` function SHALL NOT raise an exception due to a stdio server connection failure, consistent with the existing Soft_Fail behavior for HTTP servers (existing R5.5).
4. WHEN a stdio server fails, THE MCP_Loader SHALL include the failure in the `MCPLoadResult.failures` list as a tuple of `(server_name, error_message)` where `error_message` follows the format `"{ExceptionType}: {message}"`, consistent with the format used for HTTP server failures.
5. IF all configured MCP servers (both HTTP and stdio) fail to connect, THEN THE MCP_Loader SHALL return an MCPLoadResult with an empty tools list, an empty clients list, and all failures recorded, and the Agent SHALL continue startup without any MCP tools registered.
6. IF the Child_Process for a stdio server does not complete startup within the configured `connect_timeout_seconds`, THEN THE MCP_Loader SHALL treat the timeout as a connection failure and apply the same Soft_Fail behavior as criterion 1.

### Requirement 5: Stdio Server Lifecycle Management

**User Story:** As an Operator, I want stdio MCP server child processes to be properly terminated when the Agent shuts down, so that no orphaned processes remain after the Agent exits.

#### Acceptance Criteria

1. WHEN the Agent shuts down (via CLI exit, Web Backend shutdown, or process termination), THE AgentBundle `__exit__` method SHALL invoke `client.stop()` on every MCPClient instance in its `mcp_clients` list, including both stdio and HTTP clients, ensuring consistent cleanup regardless of transport type.
2. WHEN `client.stop()` is called on a stdio MCPClient, THE MCPClient SHALL send a termination signal to the Child_Process and wait up to 5 seconds for the process to exit gracefully, and IF the Child_Process does not exit within that 5-second period, THEN THE MCPClient SHALL forcefully kill the Child_Process. The 5-second timeout SHALL apply independently to each Child_Process. IF the forceful kill itself fails or the process becomes unkillable, THEN THE AgentBundle SHALL log a WARNING-level record naming the server and the error, and SHALL continue with remaining cleanup operations.
3. IF a Child_Process has already exited before the shutdown sequence begins, THEN THE AgentBundle SHALL skip termination for that process without raising an error.
4. IF termination of a Child_Process raises an exception (such as `OSError` or `ProcessLookupError`), THEN THE AgentBundle SHALL log a WARNING-level record naming the server and the error, and SHALL continue terminating remaining MCPClient instances without propagating the exception.
5. THE AgentBundle `__exit__` method SHALL attempt to stop all MCPClient instances regardless of individual failures, such that a failure to stop one client does not prevent the remaining clients from being stopped.

### Requirement 6: Documentation Updates

**User Story:** As an Operator, I want the README to document how to configure stdio MCP servers, so that I can add local tool servers to my Agent without reading the source code.

#### Acceptance Criteria

1. THE `README.md` SHALL document the stdio server configuration schema, including the `"type": "stdio"` field, the required `"command"` field (string, the executable to run), the optional `"args"` field (array of strings, defaults to empty array when absent), the optional `"env"` field (object of string key-value pairs, defaults to empty object when absent), and the optional `"disabled"` field (boolean), with a complete example entry in a fenced JSON code block that demonstrates all four fields.
2. THE `README.md` SHALL provide at least one end-to-end example showing a complete `mcp.json` file that contains both an HTTP server entry (with `"type": "http"` and a `"url"` field) and a stdio server entry (with `"type": "stdio"` and a `"command"` field), formatted as a fenced JSON code block with valid JSON syntax.
3. THE `README.md` SHALL document the lifecycle behavior of stdio servers, stating that Child_Processes are spawned when the Agent starts, terminated gracefully when the Agent shuts down, and forcefully terminated if the Child_Process does not exit within 5 seconds of the graceful termination attempt.
4. THE `README.md` SHALL document the Soft_Fail behavior for stdio servers, explaining that a failed stdio server does not prevent the Agent from starting, that remaining servers' tools are still loaded, and that the Operator will see a WARNING-level log record containing the server name, the command that failed, and the error description.
5. THE `README.md` SHALL document at least three failure scenarios for stdio servers (command not found, permission denied, server crashes after startup) and for each scenario SHALL describe the trigger condition and state that the Operator will observe a warning message identifying the server name and the nature of the failure.
