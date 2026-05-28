# strands-bedrock-agent

A runnable AI Agent application built on the [Strands Agents SDK](https://strandsagents.com/) that uses an Anthropic Claude Opus model hosted on [Amazon Bedrock](https://aws.amazon.com/bedrock/) as its language model. The Agent integrates the [AWS Knowledge MCP Server](https://knowledge-mcp.global.api.aws) as a tool source so it can answer questions grounded in current, authoritative AWS documentation.

## Prerequisites

- **Python 3.10** or higher
- An **AWS account** with Amazon Bedrock access enabled
- **Claude Opus** model available in the configured Region (see [Bedrock model access](#bedrock-model-access))
- Configured **AWS credentials** with `bedrock:InvokeModel` permission

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
```

On macOS / Linux:

```bash
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

2. Install the project and development dependencies:

```bash
pip install -e ".[dev]"
```

3. Configure AWS credentials (if not already configured):

```bash
aws configure
```

Ensure the configured profile has `bedrock:InvokeModel` permission for the target Region.

4. Create the MCP server configuration file at `.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "aws-knowledge-mcp-server": {
      "url": "https://knowledge-mcp.global.api.aws",
      "type": "http",
      "disabled": false
    }
  }
}
```

## Bedrock model access

Serverless foundation models on Amazon Bedrock are now automatically enabled across all AWS commercial regions when first invoked in your account — no manual activation is required. The Model access page in the Bedrock console has been retired.

**Notes:**

- For Anthropic models, first-time users may need to submit use case details before they can access the model.
- For models served from AWS Marketplace, a user with AWS Marketplace permissions must invoke the model once to enable it account-wide for all users.
- Account administrators retain full control over model access through [IAM policies](https://docs.aws.amazon.com/bedrock/latest/userguide/security-iam.html) and [Service Control Policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html) to restrict access as needed.

To get started, simply select a model from the [Model catalog](https://console.aws.amazon.com/bedrock/home#/model-catalog) and open it in the playground, or invoke the model using the [InvokeModel](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModel.html) or [Converse](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html) API operations.

The supported model identifiers are:

| Model | Bedrock cross-region inference profile ID |
|---|---|
| Claude Opus 4.5 | `global.anthropic.claude-opus-4-5-20251101-v1:0` |
| Claude Opus 4.6 | `global.anthropic.claude-opus-4-6-v1` |

The default model ID used by this project is:

```
global.anthropic.claude-opus-4-5-20251101-v1:0
```

Override it by setting the `BEDROCK_MODEL_ID` environment variable.

## Configuration

All configurable values can be set via environment variables. CLI flags (where applicable) take highest precedence, followed by environment variables, then documented defaults.

| Knob | Env var | Default | Accepted values |
|---|---|---|---|
| Bedrock model ID | `BEDROCK_MODEL_ID` | `global.anthropic.claude-opus-4-5-20251101-v1:0` | 1–256 character string |
| AWS Region | `AWS_REGION` / `AWS_DEFAULT_REGION` | *(none — must be set)* | AWS Region format, e.g. `us-east-1` |
| AWS profile | `AWS_PROFILE` | *(none — uses default chain)* | Profile name in `~/.aws/config` |
| Log level | `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL` |
| MCP config path | `MCP_CONFIG_PATH` | `.kiro/settings/mcp.json` | File path string |
| MCP connect timeout | `MCP_CONNECT_TIMEOUT_SECONDS` | `10` | Positive integer (seconds) |
| MCP tool call timeout | `MCP_TOOL_TIMEOUT_SECONDS` | `30` | Positive integer (seconds) |
| Web port | `WEB_PORT` | `8765` | Integer 1024–65535 |
| Web bind host | `WEB_HOST` | `127.0.0.1` | IP address |
| Web request timeout | `WEB_REQUEST_TIMEOUT_SECONDS` | `120` | Positive integer (seconds) |
| Max prompt length | `MAX_PROMPT_LENGTH` | `10000` | Positive integer |

## Running the CLI

The CLI is installed as the `strands-bedrock-agent` console script. You can also run it via `python -m strands_bedrock_agent`.

### Single-prompt mode

```bash
strands-bedrock-agent --prompt "What is Amazon S3?"
```

Sample response:

```
Amazon S3 (Simple Storage Service) is an object storage service offered by AWS
that provides industry-leading scalability, data availability, security, and
performance. You can use it to store and retrieve any amount of data at any time
from anywhere on the web.
```

Expected log output at the default `INFO` level (written to stderr):

```json
{"ts":"2025-04-01T12:34:56.789012+00:00","level":"INFO","event":"config.resolved","logger":"strands_bedrock_agent.agent_factory","model_id":"us.anthropic.claude-opus-4-5-20251101-v1:0","region":"us-west-2","aws_profile":null,"log_level":"INFO","mcp_config_path":".kiro/settings/mcp.json"}
{"ts":"2025-04-01T12:34:57.000000+00:00","level":"INFO","event":"mcp.connect","logger":"strands_bedrock_agent.mcp_loader","server_name":"aws-knowledge-mcp-server","endpoint":"https://knowledge-mcp.global.api.aws","outcome":"connected"}
{"ts":"2025-04-01T12:34:57.100000+00:00","level":"INFO","event":"bedrock.invoke.start","logger":"strands_bedrock_agent.agent_factory","model_id":"us.anthropic.claude-opus-4-5-20251101-v1:0","region":"us-west-2","prompt_bytes":18}
{"ts":"2025-04-01T12:34:59.500000+00:00","level":"INFO","event":"bedrock.invoke.end","logger":"strands_bedrock_agent.agent_factory","model_id":"us.anthropic.claude-opus-4-5-20251101-v1:0","latency_ms":2400,"output_bytes":245,"stop_reason":"end_turn"}
```

### Interactive mode

```bash
strands-bedrock-agent
```

Enter prompts one per line. Type `exit`, `quit`, or press Ctrl+D (EOF) to leave.

## Running the Web UI

The Web UI is installed as the `strands-bedrock-agent-web` console script. You can also run it via `python -m strands_bedrock_agent.web`.

```bash
strands-bedrock-agent-web
```

By default the server binds to `127.0.0.1` on port `8765`. Override the port with `--port`:

```bash
strands-bedrock-agent-web --port 9000
```

Accepted port range: `1024`–`65535`.

> **Disclaimer:** The Web Chat UI is intended for local developer testing only — it is not a production-grade application.

### `/api/chat` endpoint

**Request** — `POST /api/chat` with `Content-Type: application/json`:

```json
{
  "prompt": "What is the difference between Standard and Express S3?"
}
```

**Successful response** (HTTP 200):

```json
{
  "response": "S3 Express One Zone is …",
  "tool_invocations": [
    {
      "tool_name": "search_documentation",
      "started_at": "2025-04-01T12:34:56.123456+00:00",
      "completed_at": "2025-04-01T12:34:57.456789+00:00"
    }
  ]
}
```

**Error response** (HTTP 400 or 500):

```json
{
  "error": "prompt must not be empty or whitespace-only"
}
```

## Logging

The Agent emits structured JSON log records to stderr. Each record contains a timestamp (`ts` in ISO 8601 format), log level, event name, logger name, and event-specific fields.

### Log events

| Event | Description |
|---|---|
| `config.resolved` | Startup configuration has been resolved (model ID, region, profile, log level, MCP path) |
| `bedrock.invoke.start` | A Bedrock model invocation has started |
| `bedrock.invoke.end` | A Bedrock model invocation has completed (includes latency and output size) |
| `bedrock.retry` | A Bedrock invocation is being retried due to a throttling or transient error |
| `mcp.connect` | MCP server connection attempt result (connected or failed) |
| `mcp.tool.start` | An MCP tool call has started |
| `mcp.tool.end` | An MCP tool call has completed (includes latency and outcome) |
| `agent.error` | An error occurred during Agent processing |

### Log levels

- **Default level:** `INFO` — logs event names and metadata (byte lengths for prompt/tool data).
- **Recommended for development:** `DEBUG` — includes full prompt text, tool call arguments, and tool results (truncated at 4096 characters per field).

Set the log level via the `LOG_LEVEL` environment variable:

```bash
export LOG_LEVEL=DEBUG
```

## AWS Knowledge MCP Server

The Agent connects to the AWS Knowledge MCP Server to search and retrieve current AWS documentation.

- **Endpoint:** `https://knowledge-mcp.global.api.aws`
- **Authentication:** No AWS credentials are required to call the MCP server itself.
- **Tools the Agent expects:**
  - `search_documentation` — search AWS documentation by query
  - `read_documentation` — read the full content of an AWS documentation page
  - `recommend` — get content recommendations for a documentation page

## Stdio MCP Servers

In addition to remote HTTP-based MCP servers, the Agent supports local stdio-based MCP servers. A stdio MCP server is a child process that communicates with the Agent over standard input and standard output using the MCP stdio transport protocol.

### Configuration schema

Each stdio server entry in `mcp.json` uses the following fields:

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | `"stdio"` | Yes | — | Identifies this entry as a stdio server |
| `command` | string | Yes | — | The executable to run (1–1024 characters) |
| `args` | array of strings | No | `[]` | Command-line arguments passed to the process (max 64 elements, each max 4096 characters) |
| `env` | object of strings | No | `{}` | Additional environment variables for the process (max 64 entries, keys max 256 characters, values max 8192 characters) |
| `disabled` | boolean | No | `false` | When `true`, the entry is skipped without spawning a process |

Complete example showing all fields:

```json
{
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"],
  "env": {
    "NODE_ENV": "production",
    "LOG_LEVEL": "info"
  },
  "disabled": false
}
```

### End-to-end `mcp.json` example

A complete configuration file with both an HTTP server and a stdio server:

```json
{
  "mcpServers": {
    "aws-knowledge-mcp-server": {
      "type": "http",
      "url": "https://knowledge-mcp.global.api.aws"
    },
    "local-filesystem-server": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"],
      "env": {
        "NODE_ENV": "production"
      }
    }
  }
}
```

Tools from all successfully connected servers (both HTTP and stdio) are combined and made available to the Agent.

### Lifecycle behavior

Stdio server child processes follow this lifecycle:

1. **Startup** — When the Agent starts, it spawns a child process for each enabled stdio server entry and establishes communication over stdin/stdout pipes.
2. **Graceful shutdown** — When the Agent shuts down (via CLI exit, Web Backend shutdown, or process termination), it sends a termination signal to each child process.
3. **Forceful termination** — If a child process does not exit within **5 seconds** of the graceful termination attempt, the Agent forcefully kills the process.

Each child process is managed independently. A failure to terminate one process does not prevent the Agent from cleaning up remaining processes.

### Soft-fail behavior

A failed stdio server does **not** prevent the Agent from starting. When a stdio server fails to connect:

- The Agent logs a **WARNING**-level record containing the server name, the command that failed, and the error description.
- Tools from all remaining successfully connected servers are still loaded and available.
- The Agent continues startup normally with whatever tools were loaded from other servers.

This is the same soft-fail behavior used for HTTP servers — a single misconfigured or unavailable server never blocks the entire Agent.

### Failure scenarios

| Scenario | Trigger | What the Operator sees |
|---|---|---|
| **Command not found** | The `command` value does not exist on the system PATH or is not installed | A warning message identifying the server name and a `FileNotFoundError` indicating the command could not be found |
| **Permission denied** | The `command` exists but the current user lacks execute permission | A warning message identifying the server name and a `PermissionError` indicating insufficient permissions |
| **Server crashes after startup** | The child process starts successfully but exits or raises an error during tool listing | A warning message identifying the server name and the error description; the child process is terminated and cleaned up before recording the failure |

In all failure scenarios, the Agent continues to operate with tools from the remaining healthy servers.
