# Requirements Document

## Introduction

This feature delivers a new AI Agent application built on the open source Strands Agents SDK. The Agent uses an Anthropic Claude Opus model hosted on Amazon Bedrock as its underlying language model and integrates the AWS Knowledge MCP server as a tool so the Agent can answer questions using authoritative AWS documentation. The deliverable is a runnable Python project (with a defined dependency set, virtual environment, configuration, and CLI entry point) that a developer can clone, configure with AWS credentials, and execute locally to interact with the Agent.

> **Open clarification (to resolve during review):** The user requested "Claude Opus 4.6". As of the latest published Anthropic / Amazon Bedrock model catalogs known to this spec, the most recent Opus variant is Claude Opus 4.5. The Bedrock model identifier is therefore captured as a configurable value (see Requirement 3) so the exact model ID can be confirmed before implementation without rewriting requirements.

## Glossary

- **Agent**: The Strands Agents SDK `Agent` instance configured in this project that accepts a user prompt, invokes the LLM, optionally calls tools, and returns a response.
- **Strands_SDK**: The open source Strands Agents Python SDK published at https://strandsagents.com/, providing the `Agent`, model provider, and MCP tool integration primitives.
- **Bedrock_Model_Provider**: The Strands Agents Bedrock model provider component that routes Agent inferences to Amazon Bedrock.
- **Bedrock**: Amazon Bedrock, the AWS managed service that hosts the Claude Opus model used by the Agent.
- **Claude_Opus_Model**: The Anthropic Claude Opus model variant served by Bedrock and used as the Agent's LLM. The exact Bedrock model identifier is configurable.
- **AWS_Knowledge_MCP_Server**: The AWS-hosted Model Context Protocol server that exposes AWS documentation search and retrieval as MCP tools (e.g., `search_documentation`, `read_documentation`, `recommend`).
- **MCP_Client**: The Strands Agents MCP client component that connects to an MCP server and exposes its tools to the Agent.
- **CLI_Entry_Point**: The command-line script (installed as a Python console entry point or runnable module) used to invoke the Agent from a terminal.
- **Project**: The Python package and surrounding repository scaffolding produced by this feature.
- **Configuration_File**: The MCP server configuration file at `.kiro/settings/mcp.json` that declares the AWS Knowledge MCP server endpoint.
- **AWS_Credentials**: The AWS access credentials (access key ID, secret access key, optional session token) and region used to authenticate calls to Bedrock.
- **Operator**: A developer or user running the Agent locally on their workstation.
- **Web_Chat_UI**: A single-page browser-based chat interface, served by the Web_Backend, that allows the Operator to send prompts to and view responses from the Agent for local testing.
- **Web_Backend**: A local HTTP server component of the Project that hosts the Web_Chat_UI, exposes a chat HTTP endpoint that accepts prompts and returns Agent responses, and constructs the Agent using the same configuration resolution logic as the CLI_Entry_Point.
- **Web_Server_Command**: The command-line script provided by the Project that starts the Web_Backend on the Operator's workstation and serves the Web_Chat_UI on the loopback interface.

## Requirements

### Requirement 1: Python Project Scaffolding

**User Story:** As an Operator, I want a self-contained Python project with a defined structure and dependency manifest, so that I can install and run the Agent reproducibly on my workstation.

#### Acceptance Criteria

1. THE Project SHALL provide a top-level directory layout containing a `src/` directory holding the Agent Python package, a `tests/` directory for automated tests, a `pyproject.toml` at the repository root, and a `README.md` at the repository root.
2. THE Project SHALL declare in `pyproject.toml` a Python interpreter version constraint that requires Python 3.10 or newer and rejects Python 3.9 or older during installation.
3. THE Project SHALL declare in `pyproject.toml` its runtime dependencies, including the Strands Agents SDK and the Strands Agents tools package required for MCP integration, with each dependency pinned to an explicit version or version range.
4. THE Project SHALL declare in `pyproject.toml` its development dependencies (test runner, linter, formatter) in a section separate from runtime dependencies, such that installing the project without development extras does not install any development dependency.
5. WHEN the Operator executes the setup steps documented in `README.md` in the listed order on a workstation that has a supported Python interpreter and network access to the configured package index, THE Project SHALL install into a Python virtual environment and exit with a success status without requiring any manual edit to files tracked by the Project.
6. IF the documented setup steps fail because the Python interpreter version is unsupported or a declared dependency cannot be resolved, THEN THE Project SHALL terminate the installation, leave the virtual environment without partially installed Project packages, and surface an error message identifying the unsupported interpreter version or the unresolved dependency name.
7. THE Project SHALL include a `.gitignore` at the repository root that excludes the virtual environment directory, Python build and distribution artifacts, Python bytecode caches, and local environment files that contain secrets, so that none of these paths appear in `git status` after a successful install.

### Requirement 2: Strands Agents SDK Integration

**User Story:** As an Operator, I want the Agent to be implemented using the Strands Agents SDK, so that I get the SDK's standard agent loop, tool calling, and observability behavior.

#### Acceptance Criteria

1. THE Project SHALL construct the Agent as an instance of the Strands Agents SDK `Agent` class during Project startup, before the Project accepts any user prompt.
2. THE Agent SHALL be configured at construction time with a non-empty system prompt of at least 50 characters that (a) names the Agent's role and (b) instructs the Agent to invoke the registered AWS Knowledge MCP tools when the user prompt references AWS services, AWS APIs, AWS documentation, or AWS error messages.
3. WHEN the Agent receives a user prompt of 1 to 10,000 characters, THE Agent SHALL execute the Strands Agents SDK agent loop and return a single final assistant response string within 60 seconds of prompt receipt.
4. IF the Agent receives a user prompt that is empty, contains only whitespace, or exceeds 10,000 characters, THEN THE Project SHALL reject the prompt without invoking the Strands Agents SDK agent loop and return an error response indicating the prompt length constraint, with no partial assistant output emitted.
5. WHEN the Project constructs the Agent, THE Project SHALL register all AWS Knowledge MCP tools defined in Requirement 5 into the Strands Agents SDK tool registry exposed by the `Agent` instance, and SHALL complete this registration before the Agent processes the first user prompt.
6. IF tool registration in criterion 5 does not complete successfully for every AWS Knowledge MCP tool defined in Requirement 5, THEN THE Project SHALL fail startup and return an error response that names each tool that failed to register, and SHALL NOT accept any user prompt.
7. IF the installed Strands Agents SDK exposes a runtime incompatibility (missing class, removed method, or incompatible signature) when the Agent is constructed or when the agent loop is invoked, THEN THE Project SHALL terminate the current operation and return an error response that names the incompatible Strands Agents SDK package and the expected version constraint, and SHALL preserve any prior persisted state without modification.
8. WHERE a startup-time Strands Agents SDK version compatibility check is implemented, IF the check itself raises an exception or fails to complete within 5 seconds, THEN THE Project SHALL log a warning that names the Strands Agents SDK package and the reason the check did not complete, SHALL continue startup, and SHALL defer failure until a runtime incompatibility described in criterion 7 is detected.

### Requirement 3: Amazon Bedrock Model Provider Configuration

**User Story:** As an Operator, I want the Agent to use a Claude Opus model hosted on Amazon Bedrock, so that inference runs against an AWS-managed Claude Opus deployment.

#### Acceptance Criteria

1. THE Agent SHALL be configured to use the Strands Agents Bedrock_Model_Provider as its sole model backend, such that all inference requests are routed to Bedrock_Model_Provider and no other model backend is invoked.
2. THE Bedrock_Model_Provider SHALL read the Claude_Opus_Model identifier from configuration in the following precedence order: (a) environment variable, (b) configuration file value, (c) documented default identifier for a Claude Opus model on Bedrock, and SHALL accept identifier strings of 1 to 256 characters.
3. THE Bedrock_Model_Provider SHALL read the target AWS Region from configuration in the following precedence order: (a) environment variable, (b) configuration file value, (c) documented default Region, and SHALL accept any AWS Region string matching the standard AWS Region format (for example, `us-east-1`, `us-west-2`).
4. WHEN the Agent issues an inference request, THE Bedrock_Model_Provider SHALL invoke Bedrock using exactly the configured Claude_Opus_Model identifier and configured Region resolved at Agent startup, without substitution or fallback to any other model or Region.
5. IF the Claude_Opus_Model identifier or AWS Region is missing from all configuration sources and no documented default is resolvable at Agent startup, THEN THE Project SHALL fail Agent startup, return a non-zero process exit code, and surface an error message that names which value (model identifier or Region) is missing and lists the configuration sources that were checked.
6. IF the configured Claude_Opus_Model identifier is not available in the configured Region at Agent startup, THEN THE Project SHALL fail Agent startup, return a non-zero process exit code, and surface an error message that includes the configured model identifier, the configured Region, and a hint to run `aws bedrock list-foundation-models` to verify availability, without retrying against any other model or Region.
7. IF a Bedrock invocation fails at runtime due to access being denied for the configured Claude_Opus_Model in the configured Region, THEN THE Bedrock_Model_Provider SHALL stop the inference request, propagate an error to the Agent that identifies the model identifier and Region, and SHALL NOT retry against any other model or Region.
8. THE Project SHALL document, in the `README.md`, the steps required to enable Claude Opus model access in the Bedrock console for the target Region, including the names of the configuration variables for the model identifier and Region and their documented default values.

### Requirement 4: AWS Credentials and Region Configuration

**User Story:** As an Operator, I want the Agent to use my standard AWS credentials and a configurable Region, so that I do not have to embed secrets in source code and I can target the Region where my Bedrock access is enabled.

#### Acceptance Criteria

1. THE Project SHALL resolve AWS_Credentials using the AWS SDK default credential provider chain, checking sources in this order: environment variables, shared credentials file, named profile, and IAM role.
2. THE Project SHALL accept the AWS Region from, in priority order: an explicit configuration value, the `AWS_REGION` environment variable, and the active AWS profile's configured region.
3. IF no AWS Region is provided by any of the sources listed in criterion 2, THEN THE Project SHALL exit with a non-zero status within 5 seconds of startup and emit an error message that lists each Region source that was checked and indicates that no value was found.
4. WHERE the Operator supplies an AWS named profile via configuration, THE Project SHALL use that profile when resolving AWS_Credentials and SHALL ignore other credential sources in the default provider chain.
5. THE Project SHALL NOT store AWS_Credentials in source-controlled files, including configuration files, source code, and test fixtures committed to the repository.
6. IF AWS_Credentials cannot be resolved at startup after checking all sources in the default provider chain, THEN THE Project SHALL exit with a non-zero status within 5 seconds of startup and emit an error message that names each credential source that was checked and indicates that no valid credentials were found.
7. IF the resolved AWS_Credentials lack permission to invoke Bedrock for the configured Claude_Opus_Model, THEN THE Agent SHALL surface the underlying AWS authorization error to the Operator without retrying and SHALL exit with a non-zero status.
8. IF the configured AWS named profile does not exist in the shared credentials or config file, THEN THE Project SHALL exit with a non-zero status within 5 seconds of startup and emit an error message that names the missing profile.

### Requirement 5: AWS Knowledge MCP Server Tool Integration

**User Story:** As an Operator, I want the Agent to use the AWS Knowledge MCP server as a tool, so that the Agent can answer questions using current AWS documentation rather than only its training data.

#### Acceptance Criteria

1. THE Project SHALL include a Configuration_File at `.kiro/settings/mcp.json` that declares the AWS_Knowledge_MCP_Server endpoint URL and the session parameters required by the Strands Agents MCP_Client to establish a session with that endpoint.
2. WHEN the Project starts, THE MCP_Client SHALL initiate a connection to the AWS_Knowledge_MCP_Server declared in the Configuration_File and complete the connection within 10 seconds before the Agent processes the first prompt.
3. WHEN the MCP_Client successfully connects to the AWS_Knowledge_MCP_Server, THE MCP_Client SHALL retrieve the server's available tools and register each retrieved tool with the Agent before the Agent processes the first prompt.
4. WHEN the Agent invokes an AWS_Knowledge_MCP_Server tool, THE MCP_Client SHALL forward the tool call to the AWS_Knowledge_MCP_Server and return the server's response to the Agent within 30 seconds of the call being issued.
5. IF the MCP_Client does not establish a connection to the AWS_Knowledge_MCP_Server within 10 seconds at startup, or receives a connection error from the configured endpoint, THEN THE Project SHALL log a warning that names the configured server endpoint and the underlying connection error, continue startup without any AWS_Knowledge_MCP_Server tools registered with the Agent, and emit a message to the Operator on the standard interactive output indicating that AWS documentation tools are unavailable for the current session.
6. IF the AWS_Knowledge_MCP_Server returns an error response for a tool call, THEN THE MCP_Client SHALL return the error, including the server-provided error description, to the Agent without retrying, so that the Agent can decide whether to retry, fall back, or report the error to the Operator.
7. IF the AWS_Knowledge_MCP_Server does not return a response to a tool call within 30 seconds, THEN THE MCP_Client SHALL cancel the call and return a timeout error indication to the Agent that names the tool that was invoked.
8. THE Project SHALL document, in the `README.md`, the AWS_Knowledge_MCP_Server endpoint, its public availability status (no AWS credentials required to call the MCP server itself), and the list of tools the Agent expects to use.

### Requirement 6: Runnable CLI Entry Point

**User Story:** As an Operator, I want a single command that starts the Agent and lets me send it prompts, so that I can interact with the Agent from a terminal without writing additional code.

#### Acceptance Criteria

1. THE Project SHALL provide a CLI_Entry_Point installable as a Python console script declared in `pyproject.toml` and runnable as `python -m <package_name>` as a fallback, where the console script name contains only lowercase ASCII letters, digits, and hyphens and is between 1 and 64 characters long.
2. WHEN the Operator runs the CLI_Entry_Point with a `--prompt` argument whose value is a non-empty string of 1 to 10000 characters, THE Agent SHALL process the supplied prompt exactly once, print the final response to standard output, and THE CLI_Entry_Point SHALL exit with status 0 within 120 seconds of the Agent producing the final response.
3. IF the Operator runs the CLI_Entry_Point with a `--prompt` argument whose value is empty or exceeds 10000 characters, THEN THE CLI_Entry_Point SHALL print an error message to standard error indicating the prompt length is invalid and exit with a non-zero status without invoking the Agent.
4. WHEN the Operator runs the CLI_Entry_Point without a `--prompt` argument, THE CLI_Entry_Point SHALL enter an interactive read-evaluate-print loop that reads one prompt per line from standard input (each up to 10000 characters), prints each Agent response to standard output, and continues until the Operator enters one of the exit commands `exit` or `quit` or sends end-of-file (EOF), at which point THE CLI_Entry_Point SHALL exit with status 0.
5. WHEN the Operator runs the CLI_Entry_Point with a `--help` argument, THE CLI_Entry_Point SHALL print usage information to standard output that lists every supported argument with its name, whether it is required, and a one-line description, and exit with status 0 within 5 seconds without invoking the Agent.
6. WHILE the Agent is processing a prompt in interactive mode, THE CLI_Entry_Point SHALL display a visible progress indicator on standard error that updates at least once every 1 second until the Agent returns a response or an error.
7. IF the Agent raises an unhandled exception while processing a prompt in single-prompt mode, THEN THE CLI_Entry_Point SHALL print an error message to standard error indicating the failure cause and exit with a non-zero status without printing a partial response to standard output.
8. IF the Agent raises an unhandled exception while processing a prompt in interactive mode, THEN THE CLI_Entry_Point SHALL print an error message to standard error indicating the failure cause, discard any partial response, and return to the interactive prompt to accept the next input.
9. IF the CLI_Entry_Point cannot write the error message to standard error in interactive mode, THEN THE CLI_Entry_Point SHALL exit with a non-zero status rather than continuing in an inconsistent state.

### Requirement 7: Error Handling and Observability

**User Story:** As an Operator, I want clear logs and structured error handling, so that I can diagnose configuration, network, and model failures without reading the SDK source.

#### Acceptance Criteria

1. THE Project SHALL emit structured log records, each containing a timestamp in ISO 8601 format, log level, event name, and event-specific fields, for the following events: startup configuration resolution, Bedrock model invocation start, Bedrock model invocation completion, MCP server connection, MCP tool call start, MCP tool call completion, and Agent error.
2. THE Project SHALL allow the Operator to set the log level via a `LOG_LEVEL` environment variable that accepts the standard Python logging levels (DEBUG, INFO, WARNING, ERROR, CRITICAL), defaulting to INFO when the variable is unset or empty.
3. IF the `LOG_LEVEL` environment variable is set to a value other than DEBUG, INFO, WARNING, ERROR, or CRITICAL (case-insensitive), THEN THE Project SHALL fall back to the INFO level and emit one WARNING log record indicating that the supplied value was invalid.
4. WHILE the log level is set to DEBUG, THE Project SHALL include the full prompt text, tool call arguments, and tool call results in the corresponding log records, truncated to a maximum of 4096 characters per field with a truncation marker appended when truncation occurs.
5. WHILE the log level is set to INFO, WARNING, ERROR, or CRITICAL, THE Project SHALL exclude prompt content, tool call arguments, and tool call results from log records and SHALL instead record only the byte length of each excluded field.
6. WHEN a Bedrock invocation fails with a throttling or transient error, THE Bedrock_Model_Provider SHALL retry using its built-in retry behavior and SHALL emit one WARNING log record per retry attempt containing the attempt number, the model identifier, and the AWS error code.
7. IF a Bedrock invocation fails after all retries are exhausted, THEN THE Agent SHALL surface the error to the CLI_Entry_Point with a non-zero exit code and a single error message that names the model identifier and the AWS error code, without including stack traces or AWS credential values.
8. IF an MCP tool call fails or the MCP server connection is lost, THEN THE Project SHALL emit one ERROR log record naming the MCP server, the tool name (when available), and the failure category, and THE Agent SHALL continue running so the Operator can issue further prompts.
9. THE Project SHALL document, in the `README.md`, the meaning of each log event listed in criterion 1, the default log level, and the recommended log level for development versus production-like use.

### Requirement 8: Project Documentation

**User Story:** As an Operator new to the Project, I want a README that walks me through setup and first invocation, so that I can run the Agent successfully on my first attempt.

#### Acceptance Criteria

1. THE `README.md` SHALL describe the Project's purpose in 1 to 5 sentences and SHALL list the Strands_SDK dependency, the Bedrock dependency, and the AWS_Knowledge_MCP_Server tool integration with a one-sentence description of each.
2. THE `README.md` SHALL list the prerequisites required to run the Agent, including the exact required Python version (e.g., Python 3.10 or higher), an AWS account with Amazon Bedrock access enabled, Claude Opus model access in the configured Region, and configured AWS credentials with permission to invoke Bedrock.
3. THE `README.md` SHALL provide numbered, step-by-step setup instructions covering virtual environment creation, dependency installation, AWS credential configuration, and `.kiro/settings/mcp.json` configuration, where each step includes the exact command or file content the Operator must execute or create.
4. THE `README.md` SHALL provide at least one end-to-end example invocation that includes the exact command to run, a sample prompt, a representative sample Agent response, and the expected log output at the default log level, with all four elements shown in copy-pasteable code blocks.
5. THE `README.md` SHALL document each configurable value (model identifier, Region, log level, AWS profile) in a single table or list that specifies, for each value, the environment variable name, the default value, and the set of accepted values or accepted format.
6. IF an Operator follows the documented setup steps in order on a supported environment matching the listed prerequisites, THEN THE `README.md` example invocation SHALL produce output matching the documented sample response and log output without requiring additional undocumented steps.
7. WHEN the README documents a command, configuration snippet, or environment variable, THE `README.md` SHALL render that content in a fenced code block so the Operator can copy it without manual reformatting.

### Requirement 9: Frontend Chatbot Web UI for Local Testing

**User Story:** As an Operator, I want a simple browser-based chat interface served by a local web server, so that I can test the Agent interactively without using the CLI and observe when the Agent invokes AWS Knowledge MCP tools.

#### Acceptance Criteria

1. THE Project SHALL provide a Web_Server_Command that is installable as a Python console script declared in `pyproject.toml` and runnable as `python -m <package_name>.web` as a fallback, where the console script name contains only lowercase ASCII letters, digits, and hyphens, is between 1 and 64 characters long, and does not start or end with a hyphen.
2. WHEN the Operator runs the Web_Server_Command without arguments, THE Web_Backend SHALL start an HTTP server bound to the loopback address `127.0.0.1` on a documented default port in the range 1024 to 65535 and SHALL serve the Web_Chat_UI as a single HTML page at the root path `/` within 10 seconds of process start, and SHALL print to standard output a single startup line containing the bound address and port.
3. WHEN the Operator runs the Web_Server_Command with a `--port` argument whose value is an integer between 1024 and 65535 inclusive, THE Web_Backend SHALL bind to that port on `127.0.0.1`.
4. IF the `--port` argument value is not an integer, is outside the inclusive range 1024 to 65535, or the requested port is already in use, THEN THE Web_Server_Command SHALL print an error message to standard error that names the validation failure and the accepted port range, SHALL exit with a non-zero status within 5 seconds, and SHALL NOT start the HTTP server or accept any TCP connections.
5. THE Web_Backend SHALL bind exclusively to the loopback interface `127.0.0.1` by default, SHALL NOT bind to `0.0.0.0` or any non-loopback interface unless the Operator passes an explicit opt-in flag, and SHALL document the loopback-only default behavior in the `README.md`.
6. THE Web_Backend SHALL construct the Agent using the same configuration resolution logic that the CLI_Entry_Point uses, including the Claude_Opus_Model identifier resolution defined in Requirement 3, the AWS Region and AWS_Credentials resolution defined in Requirement 4, and the AWS_Knowledge_MCP_Server connection and tool registration defined in Requirement 5.
7. THE Web_Backend SHALL expose a single HTTP POST endpoint at the path `/api/chat` that accepts a JSON request body containing a `prompt` field of type string with length 1 to 10000 characters and returns a JSON response body containing a `response` field with the Agent's final assistant response and a `tool_invocations` field listing each AWS_Knowledge_MCP_Server tool invocation made while producing the response, where each list entry contains the tool name and the invocation start and completion timestamps in ISO 8601 format with UTC offset.
8. IF the `/api/chat` endpoint receives a request whose body is not valid JSON, whose `Content-Type` is not `application/json`, or whose `prompt` field is missing, is not a string, is empty, contains only whitespace, or exceeds 10000 characters, THEN THE Web_Backend SHALL return an HTTP 400 response with a JSON body containing an `error` field that names the validation failure and SHALL NOT invoke the Agent.
9. WHEN the Web_Chat_UI receives a non-empty prompt entered by the Operator and the Operator triggers send, THE Web_Chat_UI SHALL POST the prompt to the `/api/chat` endpoint, display the Agent's `response` text in the chat transcript, and display each entry from the `tool_invocations` list as a distinct visible item labeled with the tool name and the invocation start timestamp.
10. WHILE the Web_Backend is processing a prompt for which the `/api/chat` response has not yet been received, THE Web_Chat_UI SHALL display a visible in-progress indicator and SHALL prevent the Operator from submitting an additional prompt until the in-progress request completes, fails, or the Web_Chat_UI's request timeout of 120 seconds elapses.
11. IF the Agent raises a Bedrock invocation error, an AWS_Knowledge_MCP_Server tool error, a request processing timeout exceeding 120 seconds, or any other unhandled exception while processing a prompt received via `/api/chat`, THEN THE Web_Backend SHALL return an HTTP 500 response with a JSON body containing an `error` field naming the failure category and a single human-readable message excluding stack traces and AWS_Credentials values, and THE Web_Chat_UI SHALL display the returned error message in the chat transcript without reloading or unloading the page.
12. THE Web_Backend SHALL emit the structured log records defined in Requirement 7 for every prompt received via `/api/chat`, including startup configuration resolution, Bedrock model invocation start and completion, MCP tool call start and completion, and Agent error events, using the same log format and `LOG_LEVEL` configuration defined in Requirement 7.
13. THE `README.md` SHALL document the Web_Server_Command, the default loopback bind address `127.0.0.1`, the default port value, the `--port` argument accepted inclusive range 1024 to 65535, the `/api/chat` endpoint request and response JSON shapes, and an explicit statement that the Web_Chat_UI is intended for local developer testing only and is not a production-grade application.
