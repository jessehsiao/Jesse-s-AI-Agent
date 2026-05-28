# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An AI Agent application built on the [Strands Agents SDK](https://strandsagents.com/) that uses Claude Opus on Amazon Bedrock as its LLM. It connects to the [AWS Knowledge MCP Server](https://knowledge-mcp.global.api.aws) to answer questions grounded in AWS documentation. Supports both a CLI (single-prompt and interactive REPL) and a FastAPI web backend with chat UI.

## Commands

```bash
# Install (editable mode with dev deps)
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_config_unit.py

# Run a single test by name
pytest tests/test_config_unit.py -k "test_name"

# Lint
ruff check src/ tests/

# Format
black src/ tests/

# Run CLI (single prompt)
strands-bedrock-agent --prompt "What is Amazon S3?"

# Run CLI (interactive REPL)
strands-bedrock-agent

# Run web server
strands-bedrock-agent-web --port 8765
```

## Architecture

### Source layout (`src/strands_bedrock_agent/`)

The application has a layered design where both CLI and Web surfaces share the same agent construction path:

- **`config.py`** — Resolves all configuration with precedence: CLI args > env vars > file > defaults. Returns a frozen `Config` dataclass. Region resolution chains through AWS_REGION, AWS_DEFAULT_REGION, then boto3 profile.
- **`agent_factory.py`** — Single `build_agent(config)` function used by both CLI and Web. Returns an `AgentBundle` (context manager) holding the Agent, MCP clients, and tool invocation recording. Construction order: boto3 session → model availability check → BedrockModel → MCP tools → strands.Agent.
- **`mcp_loader.py`** — Parses `.kiro/settings/mcp.json`, constructs `MCPClient` instances for HTTP and stdio servers. Soft-fail: a broken server logs a warning but doesn't block startup. Clients are NOT started here — the Strands SDK manages lifecycle via ToolProvider interface.
- **`cli.py`** — Argparse entry point. Single-prompt mode writes response to stdout and exits. Interactive mode shows a spinner and continues on errors.
- **`web/server.py`** — FastAPI app with `POST /api/chat` endpoint. Uses `asyncio.wait_for` with configurable timeout. Serves static chat UI from `web/static/`.
- **`web/schemas.py`** — Pydantic request/response models for the API.
- **`errors.py`** — Error taxonomy with structured classes, exit code mapping, and credential-sanitizing `render_error()`.
- **`logging_setup.py`** — Structured JSON logging to stderr. At INFO level, protected fields (prompt, tool_args, tool_result) are replaced with byte counts. At DEBUG, they're truncated at 4096 chars.
- **`system_prompt.py`** — The agent's system prompt instructing it to use MCP tools for AWS questions.

### Key design decisions

- **MCP config lives at `.kiro/settings/mcp.json`** — supports both `"type": "http"` (remote) and `"type": "stdio"` (local child process) servers.
- **MCPClients are passed as ToolProviders** to `strands.Agent(tools=...)` — the SDK calls `start()` and `load_tools()` internally.
- **Tool invocation recording** uses thread-local storage on `AgentBundle` so the web layer can report timing per request.
- **Error rendering sanitizes AWS access keys** (regex strips AKIA/ASIA patterns) and traceback headers before showing to operators.

### Test conventions

Tests use `pytest` with `hypothesis` for property-based testing. Test files follow the naming pattern:
- `test_<module>_unit.py` — deterministic unit tests
- `test_<module>_property<N>.py` — property-based tests (numbered by requirement)

The project uses `pytest-asyncio` with `asyncio_mode = "auto"`.

## Environment Variables

Required: `AWS_REGION` (or `AWS_DEFAULT_REGION`, or a boto3 profile with region configured).

Key optional vars: `BEDROCK_MODEL_ID`, `LOG_LEVEL`, `MCP_CONFIG_PATH`, `WEB_PORT`, `MAX_PROMPT_LENGTH`.

## Style

- Line length: 100 (black + ruff)
- Target: Python 3.10+
- Ruff rules: E, F, W, I, B, UP
