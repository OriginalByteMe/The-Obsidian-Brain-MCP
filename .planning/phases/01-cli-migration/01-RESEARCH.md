# Phase 1: CLI Migration - Research

**Researched:** 2026-03-08
**Domain:** MCP SDK migration (mcp-use -> FastMCP) + Obsidian CLI backend (REST API -> subprocess)
**Confidence:** HIGH

## Summary

Phase 1 replaces two foundational dependencies: the `mcp-use` server framework with the official `mcp` SDK (FastMCP), and the `httpx`-based REST API client with Obsidian CLI subprocess calls. The official Obsidian CLI shipped in v1.12.0 (early access Feb 10, 2026) and became GA in v1.12.4 (Feb 27, 2026). It operates as a remote control for a running Obsidian instance -- it is NOT headless. If Obsidian is not running, the CLI auto-launches it.

The CLI provides native commands for all core vault operations: read, create, append, delete, move, search, daily notes, properties, tags, backlinks, and orphan detection. It supports `format=json` output for scripting. This covers the majority of the existing REST API surface, with some gaps (DQL/JsonLogic search, periodic notes beyond daily, PATCH-style heading-targeted operations).

The MCP SDK (`mcp` package v1.26.0) provides `FastMCP` via `from mcp.server.fastmcp import FastMCP`. The decorator API (`@mcp.tool()`, `@mcp.resource()`) is nearly identical to the current `mcp-use` pattern, making the server migration straightforward.

**Primary recommendation:** Implement a `VaultClient` Protocol with `ObsidianCLIClient` as the sole implementation, using `asyncio.create_subprocess_exec` for all CLI calls with `format=json` output parsing. Drop tools that lack CLI equivalents (DQL search, JsonLogic search, non-daily periodic notes). Migrate server from `mcp-use` to `mcp` SDK simultaneously.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- REST backend is deleted entirely after migration -- not kept as fallback
- VaultClient Protocol defines the interface (for testability and clean boundaries)
- ObsidianCLIClient implements the Protocol
- Snapshot current REST behavior as integration tests before migration begins -- these become the migration contract
- No `OBSIDIAN_BACKEND` env var -- CLI is the only backend, no switching needed
- `httpx`, `mcp-use`, and `pytest-httpx` removed from dependencies
- Hard error if Obsidian CLI binary not found at startup -- server refuses to start
- Also check for running Obsidian instance if CLI requires it (research confirms: CLI requires running Obsidian)
- CLI binary located via PATH lookup by default, with `OBSIDIAN_CLI_PATH` env var override
- Error message shows full diagnostic: binary path searched, vault path configured, Obsidian running status, and link to Obsidian 1.8+ download
- Philosophy: CLI is the truth -- only expose what CLI natively supports
- DQL (Dataview) and JsonLogic search -- drop (CLI doesn't support them)
- Text search -- keep (CLI has native `obsidian search` command)
- Periodic notes (daily/weekly/monthly) -- daily only (CLI has `daily:read`, `daily:append`; no weekly/monthly/quarterly/yearly commands)
- Unsupported tool modules are removed entirely -- no stubs, no "not supported" messages
- Delete Dockerfile and docker-compose.yml -- Docker is incompatible with CLI approach
- Update README in this phase -- remove Docker section, add CLI requirements (Obsidian 1.8+, CLI on PATH)
- Update SPECIFICATION.md in this phase -- rewrite to reflect CLI backend architecture

### Claude's Discretion
- FastMCP server structure (single file vs modular register_*_tools pattern)
- CLI output parsing implementation details
- Cache refresh optimization for CLI (batch vs sequential)
- Subprocess timeout values and retry logic
- How to structure the VaultClient Protocol methods

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SDK-01 | MCP server uses official `mcp` SDK (FastMCP) | `from mcp.server.fastmcp import FastMCP` -- v1.26.0, decorator API nearly identical to mcp-use |
| SDK-02 | All existing tool registrations work with FastMCP decorator API | `@mcp.tool()` decorator compatible; `register_*_tools(server)` pattern can be preserved |
| SDK-03 | All existing resource registrations work with FastMCP | `@mcp.resource("uri://...")` decorator available; sync and async handlers both supported |
| SDK-04 | stdio transport works identically to current behavior | `mcp.run()` defaults to stdio; or explicit `mcp.run(transport="stdio")` |
| SDK-05 | `mcp-use`, `httpx`, and `pytest-httpx` removed from dependencies | Replace with `mcp>=1.26.0` in dependencies; remove httpx, mcp-use, pytest-httpx |
| CLI-01 | VaultClient Protocol defines the interface | Protocol with async methods matching current ObsidianClient's 15 methods (where CLI equivalent exists) |
| CLI-02 | ObsidianCLIClient executes vault operations via CLI subprocess calls | Use `asyncio.create_subprocess_exec("obsidian", ...)` with `format=json` |
| CLI-03 | All CLI subprocess calls are async | `asyncio.create_subprocess_exec` with `stdout=PIPE, stderr=PIPE` |
| CLI-04 | CLI output parsing isolated in dedicated parser module | Create `parsers.py` module to handle JSON output from each CLI command |
| CLI-05 | All subprocess calls have explicit timeouts | `asyncio.wait_for(proc.communicate(), timeout=30)` pattern |
| CLI-06 | Note paths sanitized before CLI invocation | Use list-form `create_subprocess_exec` (not shell=True); validate paths don't contain shell metacharacters |
| CLI-07 | Environment-based backend selection | CONTEXT.md overrides: no env var needed, CLI is the only backend. Requirement satisfied by deletion of REST. |
| CLI-08 | CLI client detects Obsidian CLI binary availability on startup | `shutil.which("obsidian")` + optional `OBSIDIAN_CLI_PATH` env var override |
| TOOL-01 | All 8 existing tool modules work with CLI backend | 6 of 8 modules have full CLI equivalents; search loses DQL/JsonLogic; daily loses non-daily periodic notes |
| TOOL-02 | Cache refresh works with CLI backend | `obsidian files ext=md format=json` for file listing; `obsidian read` for content; `obsidian tags` for tag data |
| TOOL-03 | Cache invalidates specific entries after write operations | Existing VaultCache pattern preserved; CLI writes trigger targeted cache updates |
| TOOL-04 | Existing MCP tool response shapes preserved | JSON response format maintained in tool handlers; only client layer changes |
| TOOL-05 | Integration tests capture current behavior before migration | Snapshot tests of tool outputs before any code changes |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp` | >=1.26.0 | MCP server framework (FastMCP) | Official Python MCP SDK; FastMCP is the standard server API |
| `pydantic` | >=2.0.0 | Data models and validation | Already in use; required by mcp SDK |
| `python-frontmatter` | >=1.1.0 | YAML frontmatter parsing | Already in use; no REST dependency |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pyyaml` | (transitive) | YAML parsing for memory/knowledge | Already used via python-frontmatter and directly in memory.py |

### Removed Dependencies
| Library | Was | Why Removed |
|---------|-----|-------------|
| `mcp-use` | >=1.5.1 | Replaced by official `mcp` SDK |
| `httpx` | >=0.27.0 | No more HTTP calls; CLI uses subprocess |
| `pytest-httpx` | >=0.30.0 | No HTTP mocking needed; mock subprocess instead |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `mcp` (official) | `fastmcp` (standalone v3) | Standalone fastmcp is more feature-rich but adds dependency; official SDK's built-in FastMCP is sufficient |
| `asyncio.create_subprocess_exec` | `subprocess.run` in thread pool | Native async subprocess is cleaner for an async server; no thread pool overhead |

**Installation:**
```bash
pip install "mcp>=1.26.0" "pydantic>=2.0.0" "python-frontmatter>=1.1.0"
```

## Architecture Patterns

### Recommended Project Structure
```
src/obsidian_brain/
  server.py              # FastMCP server init + tool/resource registration
  cli_client.py          # ObsidianCLIClient (VaultClient Protocol impl)
  protocol.py            # VaultClient Protocol definition
  parsers.py             # CLI JSON output parsing functions
  cache.py               # VaultCache (reuse as-is, change data source)
  models.py              # Pydantic models (reuse as-is)
  knowledge.py           # Knowledge manager (reuse as-is)
  memory.py              # Memory manager (reuse as-is)
  onboarding.py          # Onboarding manager (reuse as-is)
  exceptions.py          # Shared exceptions (NoteNotFoundError, CLIError, etc.)
  tools/
    __init__.py
    vault.py             # KEEP - list, read, create, update, append, delete
    links.py             # KEEP - backlinks, outgoing links, graph traversal
    tags.py              # KEEP - add/remove tags, list tags, notes by tag
    search.py            # REWRITE - only text search via CLI; drop DQL + JsonLogic
    daily.py             # REWRITE - only daily notes via CLI; drop periodic (weekly/monthly/etc)
    knowledge.py         # KEEP - uses cache, not client directly (mostly)
    memory.py            # KEEP - swap client calls
    onboarding.py        # KEEP - swap client calls
  resources/
    __init__.py
    structure.py         # KEEP - cache-based, no client dependency
    knowledge.py         # KEEP - swap client calls
  utils/
    frontmatter.py       # KEEP - pure text processing
    wikilinks.py         # KEEP - pure text processing
```

### Pattern 1: VaultClient Protocol
**What:** A `typing.Protocol` that defines the async interface for vault operations, decoupling tool handlers from any specific backend.
**When to use:** Always -- all tool modules depend on the protocol, not the concrete implementation.
**Example:**
```python
# protocol.py
from typing import Protocol, Any

class VaultClient(Protocol):
    async def list_directory(self, path: str = "/") -> list[dict[str, Any]]: ...
    async def get_all_files(self, path: str = "/") -> list[str]: ...
    async def get_note(self, path: str, include_metadata: bool = True) -> dict[str, Any]: ...
    async def create_note(self, path: str, content: str) -> None: ...
    async def update_note(self, path: str, content: str) -> None: ...
    async def append_to_note(self, path: str, content: str) -> None: ...
    async def delete_note(self, path: str) -> None: ...
    async def note_exists(self, path: str) -> bool: ...
    async def search_simple(self, query: str, context_length: int = 100) -> list[dict[str, Any]]: ...
    async def get_daily_note(self, date: str | None = None) -> dict[str, Any]: ...
    async def append_daily(self, content: str, date: str | None = None) -> None: ...
    async def get_tags(self) -> dict[str, int]: ...
    async def get_backlinks(self, path: str) -> list[str]: ...
    async def get_links(self, path: str) -> list[str]: ...
```

### Pattern 2: CLI Client with Subprocess Exec
**What:** All CLI calls use `asyncio.create_subprocess_exec` with list-form arguments (never shell=True) and `format=json` output.
**When to use:** Every vault operation.
**Example:**
```python
# cli_client.py
import asyncio
import json
import shutil

class ObsidianCLIClient:
    def __init__(self, cli_path: str | None = None, vault: str | None = None, timeout: float = 30.0):
        self.cli_path = cli_path or shutil.which("obsidian") or "obsidian"
        self.vault = vault  # optional vault name for multi-vault
        self.timeout = timeout

    async def _run(self, *args: str, timeout: float | None = None) -> str:
        """Execute a CLI command and return stdout."""
        cmd = [self.cli_path, *args]
        if self.vault:
            cmd.append(f'vault={self.vault}')

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout or self.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(f"CLI command timed out after {timeout or self.timeout}s: {' '.join(cmd)}")

        if proc.returncode != 0:
            raise CLIError(proc.returncode, stderr.decode().strip(), cmd)

        return stdout.decode()

    async def _run_json(self, *args: str, timeout: float | None = None) -> Any:
        """Execute CLI command and parse JSON output."""
        output = await self._run(*args, "format=json", timeout=timeout)
        return json.loads(output)

    async def get_note(self, path: str, include_metadata: bool = True) -> dict[str, Any]:
        """Read a note via CLI."""
        output = await self._run("read", f'path="{path}"', "format=json")
        data = json.loads(output)
        # Parse and normalize to match expected format
        return {
            "path": path,
            "content": data.get("content", ""),
            "tags": data.get("tags", []),
            "frontmatter": data.get("frontmatter", {}),
            "modified": data.get("modified"),
        }
```

### Pattern 3: FastMCP Server with Modular Registration
**What:** Keep the existing `register_*_tools(server)` pattern but pass a `FastMCP` instance instead of `MCPServer`.
**When to use:** Server initialization.
**Recommendation:** Preserve the modular pattern -- it keeps tool files focused and the server.py file clean.
**Example:**
```python
# server.py
from mcp.server.fastmcp import FastMCP
from .cli_client import ObsidianCLIClient

mcp = FastMCP(
    "obsidian-brain",
    instructions="...",  # server instructions
)

# Create client singleton
client = ObsidianCLIClient()

# Register tools (pass both server and client)
register_vault_tools(mcp, client)
register_link_tools(mcp, client)
# ... etc

def main():
    mcp.run()  # defaults to stdio
```

### Pattern 4: Client Injection (Replace Context Manager)
**What:** Instead of `async with ObsidianClient() as client:` inside every tool, inject a client singleton.
**When to use:** Every tool handler.
**Why:** CLI client has no connection lifecycle -- no need for context manager. A module-level singleton or injected dependency is cleaner.
**Example:**
```python
# tools/vault.py
def register_vault_tools(server: FastMCP, client: VaultClient) -> None:
    @server.tool()
    async def get_note(path: str) -> str:
        try:
            data = await client.get_note(path, include_metadata=True)
            # ... same processing logic
        except NoteNotFoundError:
            return json.dumps({"error": True, ...})
```

### Anti-Patterns to Avoid
- **Shell=True subprocess calls:** Never use `shell=True` -- it enables command injection. Always use list-form `create_subprocess_exec`.
- **Blocking subprocess in async code:** Never use `subprocess.run()` in async handlers -- it blocks the event loop.
- **Creating new client per tool call:** The CLI client is stateless; a singleton is sufficient and avoids PATH lookups on every call.
- **Parsing CLI text output:** Always use `format=json` -- text output is fragile and varies by locale/version.
- **String interpolation for CLI args:** Never f-string paths into shell commands. Use list-form args with proper quoting.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CLI binary detection | Custom PATH walking | `shutil.which("obsidian")` | Cross-platform, handles PATH correctly |
| Async subprocess | Thread pool executor | `asyncio.create_subprocess_exec` | Native async, no thread overhead |
| JSON output parsing | Regex on CLI text output | `format=json` flag + `json.loads` | Structured, version-stable output |
| YAML frontmatter | Custom parser | `python-frontmatter` library | Already in deps, handles edge cases |
| Wikilink extraction | New regex patterns | Existing `utils/wikilinks.py` | Already tested, handles aliases and headings |
| Process timeout | Manual timer logic | `asyncio.wait_for()` | Standard library, handles cancellation correctly |
| Backlink computation | CLI `backlinks` command for cache | Existing `VaultCache._build_backlink_index` | Cache already does this; CLI backlinks is per-note only |

**Key insight:** The CLI provides per-note operations but not bulk queries. The existing VaultCache pattern of "fetch all notes, build indexes in memory" is still the right approach for backlinks, tag counts, and graph traversal. The cache just needs a different data source (CLI instead of REST).

## Common Pitfalls

### Pitfall 1: CLI Requires Running Obsidian
**What goes wrong:** CLI commands fail or hang because Obsidian is not running. The CLI auto-launches Obsidian, which may take 5-10 seconds and produce unexpected behavior.
**Why it happens:** CLI is a remote control, not a standalone tool.
**How to avoid:** At startup, verify Obsidian is running. If not, show a clear error message rather than waiting for auto-launch. Consider detecting via process list or attempting a lightweight CLI command with a short timeout.
**Warning signs:** First CLI call takes much longer than subsequent ones; stderr contains launch messages.

### Pitfall 2: Shell Injection via Note Paths
**What goes wrong:** A note path like `` `$(rm -rf ~)`.md `` could execute arbitrary commands.
**Why it happens:** Using `shell=True` or string interpolation in subprocess calls.
**How to avoid:** Always use `create_subprocess_exec` with list-form arguments. The path is passed as a single argument element, never interpolated into a shell string. Validate paths don't contain null bytes.
**Warning signs:** Any use of `os.system()`, `subprocess.run(shell=True)`, or f-strings building command strings.

### Pitfall 3: Cache Refresh Performance Regression
**What goes wrong:** Cache refresh takes 10x longer than REST because CLI calls are sequential per-note rather than batched.
**Why it happens:** REST could fetch note metadata in bulk; CLI `read` is one note at a time.
**How to avoid:** Use `obsidian files ext=md format=json` for the file listing (single call). Use `obsidian tags format=json` for tag data (single call). For note content, use bounded concurrency with `asyncio.Semaphore` to run multiple `obsidian read` calls in parallel (e.g., 10 concurrent). For backlinks, use cache-side computation from note content rather than per-note `obsidian backlinks` calls.
**Warning signs:** Cache refresh taking >30s on a 500-note vault.

### Pitfall 4: FastMCP Resource Decorator Differences
**What goes wrong:** Resources registered with `@server.resource()` fail because FastMCP's decorator signature differs from mcp-use.
**Why it happens:** FastMCP uses URI templates with `@mcp.resource("vault://structure")` and may not support `mime_type` parameter the same way.
**How to avoid:** Check the exact FastMCP resource decorator API. The current code uses `@server.resource(uri="vault://structure", mime_type="application/json")` -- verify this maps to FastMCP's API.
**Warning signs:** Import errors or registration failures at startup.

### Pitfall 5: CLI Argument Quoting
**What goes wrong:** File names with spaces or special characters fail because arguments aren't properly quoted.
**Why it happens:** CLI uses `key=value` syntax where values with spaces need quotes.
**How to avoid:** When passing values to CLI, wrap in quotes within the argument: `f'file="{path}"'` or `f'path="{path}"'`. Test with paths containing spaces, unicode, and special characters.
**Warning signs:** "file not found" errors on notes with spaces in names.

### Pitfall 6: Obsidian Version Mismatch
**What goes wrong:** CLI commands fail with cryptic errors because user has Obsidian <1.12.
**Why it happens:** CLI was added in 1.12.0 and GA in 1.12.4.
**How to avoid:** On startup, run `obsidian version` and parse the output. If version < 1.12.4, show a clear error with download instructions.
**Warning signs:** "unknown command" errors from CLI.

## Code Examples

### FastMCP Server Setup
```python
# Source: https://github.com/modelcontextprotocol/python-sdk
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "obsidian-brain",
    instructions="Obsidian Brain MCP Server - Intelligent Vault Interaction via CLI",
)

@mcp.tool()
async def get_note(path: str) -> str:
    """Get the content and metadata of a specific note."""
    # tool implementation
    ...

@mcp.resource("vault://structure")
def vault_structure() -> str:
    """Returns the cached vault structure."""
    ...

def main():
    mcp.run()  # defaults to stdio transport
```

### CLI Subprocess Pattern
```python
# Source: Python asyncio docs + Obsidian CLI docs
import asyncio
import json

async def cli_read_note(cli_path: str, note_path: str) -> dict:
    proc = await asyncio.create_subprocess_exec(
        cli_path, "read", f'path="{note_path}"', "format=json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    if proc.returncode != 0:
        raise RuntimeError(f"CLI error: {stderr.decode()}")
    return json.loads(stdout.decode())
```

### CLI Search
```python
# Source: https://frankanaya.com/obsidian-cli/
async def cli_search(cli_path: str, query: str, limit: int = 20) -> list[dict]:
    proc = await asyncio.create_subprocess_exec(
        cli_path, "search", f'query="{query}"', f"limit={limit}", "format=json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    if proc.returncode != 0:
        raise RuntimeError(f"Search failed: {stderr.decode()}")
    return json.loads(stdout.decode())
```

### CLI Daily Notes
```python
# Source: https://frankanaya.com/obsidian-cli/
async def cli_daily_read(cli_path: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        cli_path, "daily:read", "format=json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    return json.loads(stdout.decode())

async def cli_daily_append(cli_path: str, content: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        cli_path, "daily:append", f'content="{content}"',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.wait_for(proc.communicate(), timeout=30.0)
```

### Startup Validation
```python
import os
import shutil

def find_cli_binary() -> str:
    """Locate the Obsidian CLI binary."""
    # Check env var override first
    env_path = os.environ.get("OBSIDIAN_CLI_PATH")
    if env_path:
        if os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            return env_path
        raise RuntimeError(
            f"OBSIDIAN_CLI_PATH set to '{env_path}' but file not found or not executable"
        )

    # Fall back to PATH lookup
    found = shutil.which("obsidian")
    if found:
        return found

    raise RuntimeError(
        "Obsidian CLI not found.\n\n"
        "To fix this:\n"
        "1. Install Obsidian 1.12.4+ from https://obsidian.md\n"
        "2. Enable CLI: Settings > General > Command line interface\n"
        "3. Click 'Register CLI' to add to PATH\n"
        "4. Restart your terminal\n"
        "5. Verify with: obsidian version\n\n"
        "Or set OBSIDIAN_CLI_PATH=/path/to/obsidian"
    )
```

## CLI Command Mapping

This table maps every current REST client method to its CLI equivalent:

| REST Client Method | CLI Command | Status | Notes |
|-------------------|-------------|--------|-------|
| `list_directory(path)` | `obsidian files folder="{path}" format=json` | SUPPORTED | Also `obsidian folders format=tree` |
| `get_all_files(path)` | `obsidian files ext=md format=json` | SUPPORTED | Single call vs recursive REST |
| `get_note(path)` | `obsidian read path="{path}" format=json` | SUPPORTED | May need separate `properties` call for frontmatter |
| `note_exists(path)` | `obsidian read path="{path}"` (check returncode) | SUPPORTED | Non-zero exit = not found |
| `create_note(path, content)` | `obsidian create name="{name}" path="{folder}" content="{content}" --silent` | SUPPORTED | `--overwrite` flag available |
| `update_note(path, content)` | `obsidian create name="{name}" path="{folder}" content="{content}" --silent --overwrite` | SUPPORTED | create + overwrite = update |
| `append_to_note(path, content)` | `obsidian append file="{name}" content="{content}"` | SUPPORTED | No heading-targeted append |
| `patch_note(...)` | No CLI equivalent | DROPPED | Heading-targeted operations not in CLI |
| `delete_note(path)` | `obsidian delete file="{name}"` | SUPPORTED | Default uses Obsidian trash |
| `search_simple(query)` | `obsidian search query="{query}" format=json` | SUPPORTED | Native search |
| `search_dql(query)` | No CLI equivalent | DROPPED | Dataview is a plugin, not in CLI |
| `search_jsonlogic(query)` | No CLI equivalent | DROPPED | REST API specific |
| `get_periodic("daily")` | `obsidian daily:read format=json` | SUPPORTED | Daily only |
| `append_periodic("daily")` | `obsidian daily:append content="{content}"` | SUPPORTED | Daily only |
| `get_periodic(non-daily)` | No CLI equivalent | DROPPED | Weekly/monthly/quarterly/yearly not in CLI |
| `get_server_info()` | `obsidian version` | SUPPORTED | Different format |
| N/A (new) | `obsidian tags format=json` | NEW | Vault-wide tag listing |
| N/A (new) | `obsidian backlinks file="{name}" format=json` | NEW | Per-note backlinks |
| N/A (new) | `obsidian links file="{name}" format=json` | NEW | Per-note outgoing links |
| N/A (new) | `obsidian orphans format=json` | NEW | Orphan note detection |
| N/A (new) | `obsidian move file="{name}" to="{dest}"` | NEW | Rename/move with link updates |
| N/A (new) | `obsidian property:set file="{name}" name="{key}" value="{val}"` | NEW | Frontmatter property manipulation |

## Tool Module Migration Plan

| Module | Action | What Changes | What Stays |
|--------|--------|--------------|------------|
| `tools/vault.py` | KEEP + MODIFY | Replace `ObsidianClient` calls with `VaultClient` calls | All 7 tools, response shapes, error handling |
| `tools/links.py` | KEEP + MODIFY | Replace client calls; can optionally use CLI `backlinks`/`links` commands | All 4 tools, graph traversal logic |
| `tools/tags.py` | KEEP + MODIFY | Replace client calls; `list_all_tags` can use CLI `tags` command directly | All 4 tools |
| `tools/search.py` | REWRITE | Remove `search_advanced` (DQL) and `search_jsonlogic`; keep `search_content` only | `search_content` tool name and response shape |
| `tools/daily.py` | REWRITE | Remove `get_periodic_note` (non-daily); simplify daily tools to use CLI `daily:*` | `get_daily_note`, `append_to_daily`, `create_daily_entry` tool names |
| `tools/knowledge.py` | KEEP + MODIFY | Replace client calls | Both tools, knowledge generation logic |
| `tools/memory.py` | KEEP + MODIFY | Replace client calls | All 5 tools, memory management logic |
| `tools/onboarding.py` | KEEP + MODIFY | Replace client calls | All 3 tools, analysis logic |
| `resources/structure.py` | KEEP AS-IS | No changes needed -- uses cache only | Everything |
| `resources/knowledge.py` | KEEP + MODIFY | Replace client calls | Resource URI and response format |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `mcp-use` third-party SDK | Official `mcp` SDK with FastMCP | 2024-2025 | FastMCP merged into official SDK; `mcp-use` is now unnecessary |
| Obsidian Local REST API plugin | Official Obsidian CLI | Feb 2026 (v1.12) | No plugin needed; CLI is built into Obsidian |
| `httpx` async HTTP client | `asyncio.create_subprocess_exec` | This migration | Subprocess calls replace HTTP; simpler auth (no API key) |
| Docker deployment | Local-only with CLI | This migration | Docker incompatible with CLI approach; acknowledged in out-of-scope |

**Deprecated/outdated:**
- `mcp-use` package: Superseded by official `mcp` SDK; no longer needed
- Obsidian Local REST API plugin: Replaced by built-in CLI; still works but adds unnecessary dependency
- `httpx` for vault access: No HTTP needed when using CLI subprocess

## Open Questions

1. **Exact CLI JSON output shapes**
   - What we know: CLI supports `format=json` on most commands
   - What's unclear: Exact JSON structure returned by each command (field names, nesting, types)
   - Recommendation: During implementation, run each CLI command with `format=json` against a test vault and document the actual output shapes. Build parsers from real output, not assumptions. Create a test fixture file with sample outputs.

2. **CLI argument quoting edge cases**
   - What we know: Values with spaces need quotes: `file="My Note"`
   - What's unclear: How `create_subprocess_exec` interacts with CLI's key=value parsing. Does the CLI expect `file="My Note"` as a single arg or does the shell splitting matter?
   - Recommendation: Test with `create_subprocess_exec` passing `'file=My Note'` (no internal quotes, since exec doesn't use shell) vs `'file="My Note"'` (with internal quotes). The correct form depends on how Obsidian's CLI parses argv.

3. **Concurrent CLI call limits**
   - What we know: CLI operates as remote control to running Obsidian; sequential execution is documented as slow for bulk operations
   - What's unclear: Whether Obsidian handles concurrent CLI calls correctly, or if they serialize internally
   - Recommendation: Start with semaphore-bounded concurrency (5-10 parallel calls) for cache refresh. Measure actual performance on a 500-note vault. Fall back to sequential if concurrency causes errors.

4. **CLI `read` output vs REST metadata**
   - What we know: REST API returns content + tags + frontmatter + modified date in one call with JSON accept header
   - What's unclear: Whether CLI `read format=json` returns the same metadata, or just content
   - Recommendation: May need to combine `obsidian read` (content) + `obsidian properties` (frontmatter) calls. Test this early.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23.x |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/ -x --timeout=30` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SDK-01 | FastMCP server initializes | unit | `pytest tests/test_server.py::test_server_init -x` | No - Wave 0 |
| SDK-02 | Tools register on FastMCP | unit | `pytest tests/test_server.py::test_tool_registration -x` | No - Wave 0 |
| SDK-03 | Resources register on FastMCP | unit | `pytest tests/test_server.py::test_resource_registration -x` | No - Wave 0 |
| SDK-04 | stdio transport works | integration | `pytest tests/test_server.py::test_stdio_transport -x` | No - Wave 0 |
| SDK-05 | Old deps removed | unit | `pytest tests/test_dependencies.py::test_no_old_deps -x` | No - Wave 0 |
| CLI-01 | VaultClient Protocol | unit | `pytest tests/test_protocol.py -x` | No - Wave 0 |
| CLI-02 | CLI client executes commands | unit (mocked) | `pytest tests/test_cli_client.py -x` | No - Wave 0 |
| CLI-03 | Async subprocess calls | unit (mocked) | `pytest tests/test_cli_client.py::test_async_subprocess -x` | No - Wave 0 |
| CLI-04 | Parser module isolates parsing | unit | `pytest tests/test_parsers.py -x` | No - Wave 0 |
| CLI-05 | Timeout on subprocess calls | unit (mocked) | `pytest tests/test_cli_client.py::test_timeout -x` | No - Wave 0 |
| CLI-06 | Path sanitization | unit | `pytest tests/test_cli_client.py::test_path_sanitization -x` | No - Wave 0 |
| CLI-08 | CLI binary detection at startup | unit | `pytest tests/test_cli_client.py::test_binary_detection -x` | No - Wave 0 |
| TOOL-01 | Tool modules work with CLI | integration (mocked) | `pytest tests/test_tools/ -x` | No - Wave 0 |
| TOOL-02 | Cache refresh via CLI | unit (mocked) | `pytest tests/test_cache_cli.py -x` | No - Wave 0 |
| TOOL-04 | Response shapes preserved | unit | `pytest tests/test_response_shapes.py -x` | No - Wave 0 |
| TOOL-05 | Snapshot tests before migration | snapshot | `pytest tests/test_snapshots.py -x` | No - Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x --timeout=30`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_server.py` -- FastMCP server init, tool/resource registration
- [ ] `tests/test_cli_client.py` -- CLI client with mocked subprocess
- [ ] `tests/test_protocol.py` -- VaultClient Protocol conformance
- [ ] `tests/test_parsers.py` -- CLI JSON output parsing
- [ ] `tests/test_tools/` -- Tool modules with mocked client
- [ ] `tests/test_response_shapes.py` -- Response format backward compatibility
- [ ] `tests/conftest.py` -- Shared fixtures (mock client, sample CLI outputs)
- [ ] Framework install: already configured in pyproject.toml; remove `pytest-httpx`, add `pytest-timeout`

## Sources

### Primary (HIGH confidence)
- [Obsidian CLI Official Docs](https://help.obsidian.md/cli) - CLI commands, setup, requirements
- [MCP Python SDK GitHub](https://github.com/modelcontextprotocol/python-sdk) - FastMCP import path, decorator API, transport
- [MCP PyPI](https://pypi.org/project/mcp/) - Version 1.26.0, Python >=3.10, MIT license
- [kepano/obsidian-skills CLI SKILL.md](https://github.com/kepano/obsidian-skills/blob/main/skills/obsidian-cli/SKILL.md) - Authoritative CLI command reference

### Secondary (MEDIUM confidence)
- [Frank Anaya Complete CLI Guide](https://frankanaya.com/obsidian-cli/) - Detailed command reference with examples, all output formats
- [DEV.to CLI Article](https://dev.to/shimo4228/obsidians-official-cli-is-here-no-more-hacking-your-vault-from-the-back-door-3123) - CLI version history, limitations, setup instructions

### Tertiary (LOW confidence)
- CLI JSON output exact shapes: Not verified against actual CLI output; based on documentation descriptions. Must be validated during implementation.
- CLI argument quoting with create_subprocess_exec: Needs empirical testing; documentation shows shell usage, not Python subprocess.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official MCP SDK well-documented; Obsidian CLI is GA with official docs
- Architecture: HIGH - Protocol pattern is standard Python; subprocess async is well-established
- CLI command mapping: MEDIUM - Commands verified across multiple sources but exact JSON output shapes unverified
- Pitfalls: HIGH - Based on documented CLI limitations and standard subprocess security practices

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (30 days -- CLI is new but GA; MCP SDK is stable)
