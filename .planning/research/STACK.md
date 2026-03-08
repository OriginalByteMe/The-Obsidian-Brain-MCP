# Technology Stack

**Project:** Obsidian Brain v2 -- CLI Migration + Claude Code Plugin
**Researched:** 2026-03-08

## Current Stack (Preserved)

These are already in the codebase and validated. Not re-researched.

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.12+ (venv is 3.14) | Runtime |
| pydantic | 2.12.5 | Data models, validation |
| python-frontmatter | 1.1.0 | YAML frontmatter parsing |
| hatchling | latest | Build backend |
| ruff | 0.14.14 | Linting/formatting |
| mypy | 1.19.1 | Static type checking (strict) |
| pytest | 9.0.2 | Test runner |
| pytest-asyncio | 1.3.0 | Async test support |
| uv | latest | Package manager |

## Recommended Stack Changes

### 1. MCP Framework: Migrate from `mcp-use` to `mcp` (FastMCP)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| mcp (FastMCP) | 1.25.0 | MCP server framework | Official Anthropic SDK; `mcp-use` is a thin wrapper that extends `FastMCP` anyway |

**Confidence:** HIGH -- verified locally that `mcp_use.server.MCPServer` is literally `class MCPServer(FastMCP)` from the official `mcp` SDK. The official SDK is already installed as a transitive dependency (v1.25.0).

**Rationale:**
- `mcp-use` wraps `mcp.server.fastmcp.FastMCP` with added telemetry, inspector UI, and middleware. For a stdio-based MCP server, these add bloat (telemetry pings, unused HTTP routes).
- The `@server.tool()` and `@server.resource()` decorator API is identical between `mcp-use` and `FastMCP`. Migration is a one-line import change per file.
- The official SDK is maintained by Anthropic and will track MCP protocol changes first.
- Dropping `mcp-use` removes transitive dependencies: `langchain`, `langgraph`, `langsmith`, `posthog` (telemetry), `scarf_sdk` (tracking), `authlib`, `cryptography` -- significant dependency reduction.

**Migration effort:** LOW. Change `from mcp_use.server import MCPServer` to `from mcp.server.fastmcp import FastMCP`. The `run(transport="stdio")` API is identical.

### 2. Obsidian CLI Client: Replace `httpx` REST API with `asyncio.subprocess`

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| asyncio.subprocess | stdlib | Execute Obsidian CLI commands | No external dependency; CLI is a subprocess, not HTTP |
| shutil.which | stdlib | Detect CLI binary location | Verify Obsidian CLI is available before operations |

**Confidence:** MEDIUM -- Obsidian CLI (1.8+) is confirmed in project requirements but exact CLI subcommands and JSON output format need validation during implementation. Based on training data:

**What the Obsidian CLI provides (needs verification):**
- `obsidian` or `obsidian-cli` binary ships with Obsidian 1.8+
- Vault operations: read/write/list notes, search
- JSON output mode for programmatic use
- Headless mode: `--headless` flag or similar for running without GUI

**Architecture decision:** Replace the entire `ObsidianClient` class (currently httpx-based REST client) with a new `ObsidianCLIClient` that wraps subprocess calls. Keep the same async interface so tool modules need minimal changes.

```python
# New client pattern (conceptual)
import asyncio
import json

class ObsidianCLIClient:
    async def run_command(self, *args: str) -> dict:
        proc = await asyncio.create_subprocess_exec(
            self.cli_path, *args, "--format", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ObsidianCLIError(stderr.decode())
        return json.loads(stdout.decode())
```

**What to remove:**
- `httpx` -- no longer needed (REST API replaced by CLI)
- `pytest-httpx` -- no longer needed for mocking HTTP

**What to add for testing:**
- No new test dependencies needed. Mock `asyncio.create_subprocess_exec` directly with `unittest.mock.AsyncMock`.

### 3. Claude Code Plugin: Shell scripts + JSON + CLAUDE.md

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Bash/shell scripts | N/A | Hook handlers | Claude Code hooks execute shell commands; simplest integration |
| jq | system | JSON processing in hooks | Parse Claude Code hook context (JSON on stdin) |
| CLAUDE.md | N/A | Agent instructions | Claude Code reads this for project-specific behavior |

**Confidence:** MEDIUM -- Based on training data knowledge of Claude Code's plugin system. The exact hook event names and JSON schema should be verified against current Claude Code documentation.

**Claude Code Plugin Architecture (based on training data):**

Claude Code plugins consist of:

1. **Hooks** (`.claude/hooks/`): Shell scripts triggered on events
   - `PreToolUse` -- before a tool is called
   - `PostToolUse` -- after a tool returns
   - `Notification` -- on notifications
   - Configured in `.claude/settings.json` or `.claude/settings.local.json`

2. **Slash commands** (`.claude/commands/`): Custom `/commands` available in Claude Code
   - Markdown files with prompt templates
   - Can reference `$ARGUMENTS` for user input
   - File name becomes the command name (e.g., `note.md` -> `/project:note`)

3. **CLAUDE.md**: Project instructions Claude Code reads automatically
   - Root `CLAUDE.md` for project-level instructions
   - Can include references to the MCP server and vault conventions

**Plugin structure:**
```
.claude/
  commands/
    note.md          # /project:note - create a note
    search.md        # /project:search - search vault
    remember.md      # /project:remember - store a memory
  hooks/
    auto-note.sh     # Hook to detect noteworthy moments
  settings.json      # Hook configuration
CLAUDE.md            # Project instructions with vault conventions
```

**No Python needed for the plugin itself.** The plugin is shell scripts and markdown. It communicates with the MCP server (which is Python) through Claude Code's built-in MCP tool calling.

### 4. Headless Obsidian: Process management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| asyncio.subprocess | stdlib | Start/manage headless Obsidian | Launch `obsidian --headless` as background process |
| atexit | stdlib | Cleanup on exit | Ensure headless process is terminated |

**Confidence:** LOW -- Headless mode specifics (flags, startup time, vault locking) need verification against Obsidian 1.8+ documentation. This is the area with highest uncertainty.

**Key unknowns:**
- Exact command to start headless: `obsidian --headless --vault /path/to/vault`?
- Startup time before CLI commands work
- Whether headless conflicts with running Obsidian GUI
- Vault locking behavior

### 5. Logging: Add structured logging

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| logging (stdlib) | stdlib | Structured logging | Current codebase has zero logging; CLI subprocess errors need visibility |
| structlog | 25.x | Structured log formatting | Better than raw stdlib for JSON-structured log output; optional |

**Confidence:** HIGH -- stdlib logging is always available. structlog is a well-established library.

**Rationale:** The current codebase silently swallows errors (e.g., cache refresh catches all exceptions). With CLI subprocess calls replacing HTTP, error diagnostics become more important (binary not found, permission errors, vault locked, etc.).

## Complete Dependency Changes

### Add

| Package | Version | Purpose |
|---------|---------|---------|
| (none required) | | All new functionality uses stdlib |

### Remove

| Package | Reason |
|---------|--------|
| mcp-use >= 1.5.1 | Replace with official `mcp` SDK (already installed) |
| httpx >= 0.27.0 | REST API replaced by CLI subprocess |
| pytest-httpx >= 0.30.0 | No more HTTP mocking needed |

### Keep

| Package | Version | Purpose |
|---------|---------|---------|
| mcp | 1.25.0+ | Official MCP SDK (FastMCP) |
| pydantic | >= 2.0.0 | Data models |
| python-frontmatter | >= 1.1.0 | Frontmatter parsing |
| pytest | >= 8.0.0 | Testing |
| pytest-asyncio | >= 0.23.0 | Async tests |
| ruff | >= 0.4.0 | Linting |
| mypy | >= 1.10.0 | Type checking |

### Optional Add

| Package | Version | Purpose | When |
|---------|---------|---------|------|
| structlog | >= 25.0 | Structured logging | If stdlib logging proves insufficient |

## Updated pyproject.toml Dependencies

```toml
dependencies = [
    "mcp>=1.25.0",
    "pydantic>=2.0.0",
    "python-frontmatter>=1.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
]
```

**Net result:** Dependencies drop from 4 direct + ~60 transitive to 3 direct + ~20 transitive.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| MCP Framework | `mcp` (FastMCP) | `mcp-use` (current) | Unnecessary wrapper; adds telemetry, langchain deps |
| CLI Integration | asyncio.subprocess | `subprocess.run` (sync) | Server is async; blocking calls would stall the event loop |
| CLI Integration | asyncio.subprocess | `anyio.run_process` | anyio is a transitive dep of mcp, but asyncio.subprocess is simpler and sufficient |
| Plugin scripts | Bash | Python scripts | Claude Code hooks expect shell commands; Bash is simpler for JSON piping |
| Headless mgmt | asyncio.subprocess | systemd/launchd service | Over-engineered; headless should be managed by the MCP server process |
| Logging | stdlib logging | loguru | loguru is popular but adds a dependency; stdlib is sufficient |

## Installation (Post-Migration)

```bash
# Core
uv pip install mcp pydantic python-frontmatter

# Dev dependencies
uv pip install -D pytest pytest-asyncio ruff mypy
```

## Research Gaps (Need Phase-Specific Investigation)

1. **Obsidian CLI exact command interface** -- The specific subcommands, flags, and JSON output schemas need to be verified against Obsidian 1.8+ when implementation begins. This is the highest-risk area.
2. **Headless mode behavior** -- Startup time, vault locking, conflict with GUI, platform differences (Linux/macOS/Windows).
3. **Claude Code hook event schema** -- The exact JSON structure passed to hooks on stdin, available event types, and settings.json configuration format should be verified against current Claude Code docs.
4. **MCP SDK version pinning** -- The `mcp` package is at 1.25.0 currently; check for breaking changes if upgrading later.

## Sources

- Local filesystem analysis of installed packages (mcp 1.25.0, mcp-use 1.5.1)
- Source code inspection: `mcp_use.server.MCPServer` extends `mcp.server.fastmcp.FastMCP` (verified in `.venv`)
- Source code inspection: `mcp.server.fastmcp.server.py` API (tool/resource/run decorators, verified in `.venv`)
- Existing codebase: `src/obsidian_brain/client.py`, `src/obsidian_brain/server.py`
- Project requirements: `.planning/PROJECT.md`
- Training data: Claude Code plugin system (hooks, commands, CLAUDE.md) -- MEDIUM confidence
- Training data: Obsidian CLI 1.8+ capabilities -- LOW confidence, needs verification

---

*Stack research: 2026-03-08*
