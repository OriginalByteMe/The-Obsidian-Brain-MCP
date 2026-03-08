# Architecture Patterns

**Domain:** Obsidian CLI MCP Server + Claude Code Plugin
**Researched:** 2026-03-08
**Confidence:** MEDIUM (web search/fetch unavailable; based on codebase analysis + training data for Obsidian CLI and Claude Code plugin conventions)

## Recommended Architecture

The system has three distinct components that share a common vault access layer but serve different purposes and run in different contexts.

```
+--------------------------------------------------------------------+
|                        Claude Code Session                          |
|                                                                     |
|  +--------------------------+    +-----------------------------+    |
|  |   Claude Code Plugin     |    |    MCP Server (stdio)       |    |
|  |   (hooks + CLAUDE.md)    |    |    obsidian-brain           |    |
|  |                          |    |                             |    |
|  |  - Auto-detect moments   |    |  - Vault CRUD tools         |    |
|  |  - Permission prompts    |    |  - Search tools             |    |
|  |  - Slash commands        |    |  - Link/tag tools           |    |
|  |  - Memory triggers       |    |  - Memory tools             |    |
|  +-----------+--------------+    +-------------+---------------+    |
|              |                                 |                    |
+--------------+---------------------------------+--------------------+
               |                                 |
               v                                 v
+--------------------------------------------------------------------+
|                    Vault Access Layer                                |
|                                                                     |
|  +-----------------------------+                                    |
|  |   ObsidianCLIClient         |                                    |
|  |   (replaces ObsidianClient) |                                    |
|  |                             |                                    |
|  |   subprocess calls to       |                                    |
|  |   `obsidian-cli` binary     |                                    |
|  +-------------+---------------+                                    |
|                |                                                    |
|  +-------------v---------------+                                    |
|  |   Headless Process Manager  |                                    |
|  |   (optional, local only)    |                                    |
|  |                             |                                    |
|  |   Starts/stops Obsidian     |                                    |
|  |   headless when CLI needs   |                                    |
|  |   a running instance        |                                    |
|  +-------------+---------------+                                    |
|                |                                                    |
+----------------+---------------------------------------------------+
                 |
                 v
        +--------+--------+
        |  Obsidian Vault  |
        |  (filesystem)    |
        +------------------+
```

### Component Boundaries

| Component | Responsibility | Communicates With | Runtime Context |
|-----------|---------------|-------------------|-----------------|
| **MCP Server** (`server.py`) | Registers MCP tools/resources, handles stdio transport | Vault Access Layer (via CLIClient) | Long-running process, spawned by Claude Code |
| **ObsidianCLIClient** (replaces `client.py`) | Translates vault operations into CLI subprocess calls | Obsidian CLI binary, HeadlessManager | Imported by MCP server tools |
| **HeadlessManager** (new) | Lifecycle management of headless Obsidian process | Obsidian binary, OS process table | Managed by CLIClient when CLI requires running instance |
| **VaultCache** (`cache.py`) | In-memory cache of vault structure, backlink index | CLIClient (for refresh) | Singleton in MCP server process |
| **MemoryManager** (`memory.py`) | Read/write agent memories as markdown files in vault | CLIClient (via MCP tools) | Singleton in MCP server process |
| **Claude Code Plugin** (new, separate directory) | Hooks into Claude Code lifecycle, auto-detects noteworthy moments, provides slash commands | MCP server (indirectly, via Claude Code's MCP integration) | Runs as Claude Code plugin, NOT inside MCP server |

### Data Flow

**MCP Tool Call (e.g., get_note)**:
```
Claude Code Agent
  -> MCP protocol (stdio)
    -> server.py dispatches to tool handler
      -> tool handler calls ObsidianCLIClient method
        -> CLIClient spawns `obsidian-cli vault read <path>`
          -> (HeadlessManager ensures Obsidian is running if needed)
            -> CLI returns note content (stdout)
          -> CLIClient parses output, returns structured data
        -> tool handler formats response
      -> MCP protocol returns result
    -> Claude Code receives tool result
```

**Claude Code Plugin Hook (e.g., post-tool auto-memory)**:
```
Claude Code completes a tool call or conversation turn
  -> Plugin hook fires (e.g., PostToolUse or Notification)
    -> Plugin evaluates if moment is noteworthy
      -> If yes: Plugin tells Claude Code to call MCP write_memory tool
        -> Standard MCP flow to vault
      -> If no: Hook returns, no action
```

**Vault Cache Refresh**:
```
refresh_vault_structure tool called
  -> CLIClient lists all files via CLI
    -> CLIClient fetches metadata for each .md file
      -> VaultCache rebuilds folder tree, note metadata, backlink index
        -> Cache available for subsequent tag/link/search queries
```

## Current Architecture (What Exists)

The existing system has a clean layered architecture that is well-suited for the CLI migration:

```
server.py (MCP registration + stdio transport)
  |
  +-- tools/*.py (tool handlers, each registers with server)
  |     |
  |     +-- vault.py, links.py, tags.py, search.py, daily.py
  |     +-- knowledge.py, onboarding.py, memory.py
  |
  +-- resources/*.py (MCP resources: structure, knowledge)
  |
  +-- client.py (ObsidianClient - httpx async HTTP wrapper)  <-- REPLACE THIS
  |
  +-- cache.py (VaultCache - in-memory structure cache)
  |
  +-- models.py (Pydantic data models)
  |
  +-- memory.py, onboarding.py, knowledge.py (domain logic)
  |
  +-- utils/ (frontmatter.py, wikilinks.py)
```

**Key observation:** The `client.py` is the only component that touches the REST API. Every tool handler imports `ObsidianClient` and uses `async with ObsidianClient() as client:`. This means the CLI migration is a clean swap of `client.py` -- the tool handlers, cache, models, and utils are all API-transport-agnostic.

## Migration Architecture: REST to CLI

### Strategy: Interface-Preserving Replacement

The `ObsidianClient` class has a well-defined interface (see `client.py`). The replacement `ObsidianCLIClient` must implement the same async methods with the same signatures. This lets all tool handlers work without modification.

### New Module: `cli_client.py`

```python
# Replaces client.py
class ObsidianCLIClient:
    """
    Vault access via Obsidian CLI subprocess calls.

    Same interface as ObsidianClient but uses CLI instead of REST API.
    Requires Obsidian 1.8+ with CLI enabled.
    """

    def __init__(
        self,
        vault_path: str | None = None,
        cli_path: str | None = None,
    ):
        self.vault_path = vault_path or os.getenv("OBSIDIAN_VAULT_PATH", "")
        self.cli_path = cli_path or os.getenv("OBSIDIAN_CLI_PATH", "obsidian-cli")
        self._headless: HeadlessManager | None = None

    async def __aenter__(self) -> "ObsidianCLIClient": ...
    async def __aexit__(self, *args) -> None: ...

    # Same interface as ObsidianClient:
    async def list_directory(self, path: str = "/") -> list[dict[str, Any]]: ...
    async def get_note(self, path: str, include_metadata: bool = True) -> dict[str, Any]: ...
    async def create_note(self, path: str, content: str) -> None: ...
    async def update_note(self, path: str, content: str) -> None: ...
    async def append_to_note(self, path: str, content: str) -> None: ...
    async def delete_note(self, path: str) -> None: ...
    async def note_exists(self, path: str) -> bool: ...
    async def search_simple(self, query: str, context_length: int = 100) -> list[dict[str, Any]]: ...
    # etc.

    async def _run_cli(self, *args: str) -> str:
        """Run an obsidian-cli command and return stdout."""
        proc = await asyncio.create_subprocess_exec(
            self.cli_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ObsidianCLIError(proc.returncode, stderr.decode())
        return stdout.decode()
```

### New Module: `headless.py`

```python
class HeadlessManager:
    """
    Manages a headless Obsidian process for CLI access.

    Some CLI commands require a running Obsidian instance.
    This manager starts Obsidian in headless mode (no GUI)
    and keeps it alive for the duration of the MCP server session.
    """

    def __init__(self, vault_path: str):
        self.vault_path = vault_path
        self._process: asyncio.subprocess.Process | None = None

    async def ensure_running(self) -> None:
        """Start headless Obsidian if not already running."""
        ...

    async def stop(self) -> None:
        """Gracefully stop the headless process."""
        ...

    async def is_healthy(self) -> bool:
        """Check if headless process is responsive."""
        ...
```

### Migration Path in Existing Code

The tool handlers currently do:
```python
async with ObsidianClient() as client:
    result = await client.get_note(path)
```

After migration, two options:

**Option A (Recommended): Alias swap with factory function**
```python
# In client.py or a new factory module:
def get_client() -> ObsidianCLIClient | ObsidianClient:
    """Factory that returns CLI client (preferred) or REST client (fallback)."""
    if shutil.which("obsidian-cli"):
        return ObsidianCLIClient()
    return ObsidianClient()  # Legacy fallback
```

Tool handlers change one import but keep the same usage pattern. This preserves backward compatibility for users still on the REST API plugin.

**Option B: Hard swap** -- rename `ObsidianCLIClient` to `ObsidianClient` in `client.py`, delete REST code. Simpler but breaks users who haven't upgraded to Obsidian 1.8+.

**Recommendation: Option A** for the migration phase, Option B after a deprecation period.

## Claude Code Plugin Architecture

The Claude Code plugin is a **separate artifact** from the MCP server. It lives alongside the MCP server in the repository but runs in a different context.

### Plugin Directory Structure

```
claude-code-plugin/           # Top-level, separate from src/
  |
  +-- CLAUDE.md               # Plugin instructions for Claude Code
  +-- hooks/
  |     +-- post-tool-use.sh   # Fires after MCP tool calls
  |     +-- notification.sh    # Fires on conversation events
  |
  +-- commands/
  |     +-- save-memory.md     # /save-memory slash command
  |     +-- vault-status.md    # /vault-status slash command
  |     +-- remember.md        # /remember slash command
  |
  +-- config.json              # Plugin metadata and registration
```

### Plugin CLAUDE.md

This is the core of the plugin. It instructs Claude Code how to behave with the Obsidian vault. Key sections:

1. **Auto-detection rules** -- when to suggest saving to vault (e.g., after learning user preferences, after completing a significant task, when discovering project patterns)
2. **Permission model** -- always ask before writing to vault
3. **Memory conventions** -- how to structure memories (frontmatter format, naming, folder organization)
4. **Vault navigation patterns** -- how to use MCP tools effectively

### Plugin-MCP Interaction Model

The plugin does NOT call MCP tools directly. Instead:

1. Plugin hooks detect noteworthy moments
2. Plugin instructs Claude Code (via CLAUDE.md conventions) to use MCP tools
3. Claude Code calls MCP tools through the standard MCP protocol
4. The MCP server handles vault operations

This is important: the plugin is a behavioral layer (telling Claude Code WHEN and WHAT to remember), while the MCP server is the capability layer (providing HOW to interact with the vault).

```
Plugin (behavioral)  -->  Claude Code Agent  -->  MCP Server (capability)
  "This is worth           "I'll call             "Here's how to
   remembering"             write_memory"           write to vault"
```

### Plugin Hook Patterns

**PostToolUse hook** (fires after any tool call):
- Check if the completed tool produced insights worth saving
- Check if the user expressed a preference or convention
- If noteworthy, suggest (not force) saving to vault

**Notification/Session hooks**:
- On session start: read relevant memories from vault
- On session end: summarize session learnings, offer to save

## Anti-Patterns to Avoid

### Anti-Pattern 1: Plugin Directly Accessing Filesystem
**What:** Plugin scripts reading/writing vault files directly, bypassing MCP server
**Why bad:** Breaks the single-access-path guarantee (all vault access through CLI), creates race conditions with cache, loses frontmatter/wikilink handling
**Instead:** Plugin always goes through Claude Code -> MCP tools -> CLI client

### Anti-Pattern 2: Tight Coupling Between CLI Client and Tool Handlers
**What:** Tool handlers containing CLI-specific logic (parsing CLI output, handling CLI errors)
**Why bad:** Makes it impossible to swap back to REST or test without CLI
**Instead:** CLIClient returns the same data structures as the current ObsidianClient. All CLI-specific parsing stays inside `cli_client.py`.

### Anti-Pattern 3: Headless Manager as Global Singleton
**What:** HeadlessManager as a module-level singleton like VaultCache
**Why bad:** Headless process lifecycle is tied to the CLIClient session, not the module. Multiple test runs or concurrent clients would conflict.
**Instead:** HeadlessManager is owned by CLIClient instance. Created in `__aenter__`, stopped in `__aexit__`.

### Anti-Pattern 4: Plugin Storing State Outside Vault
**What:** Plugin maintaining its own state files (JSON configs, SQLite, etc.) separate from the vault
**Why bad:** Defeats the purpose -- the vault IS the persistent store. State outside vault is invisible to Obsidian and not portable.
**Instead:** All plugin state (memory, config, learned patterns) stored as notes in the `Obsidian Brain/` vault folder via MCP tools.

### Anti-Pattern 5: Synchronous CLI Calls
**What:** Using `subprocess.run()` instead of `asyncio.create_subprocess_exec()`
**Why bad:** Blocks the MCP server's event loop. Multiple concurrent tool calls would serialize.
**Instead:** Always use async subprocess. The MCP server is async (mcp-use framework), and the tool handlers are async functions.

## Patterns to Follow

### Pattern 1: Protocol/Interface Abstraction for Client

**What:** Define an abstract base class or Protocol for the vault client interface
**When:** During CLI migration, to ensure both REST and CLI clients are interchangeable

```python
from typing import Protocol, Any

class VaultClient(Protocol):
    async def __aenter__(self) -> "VaultClient": ...
    async def __aexit__(self, *args) -> None: ...
    async def list_directory(self, path: str = "/") -> list[dict[str, Any]]: ...
    async def get_note(self, path: str, include_metadata: bool = True) -> dict[str, Any]: ...
    async def create_note(self, path: str, content: str) -> None: ...
    async def update_note(self, path: str, content: str) -> None: ...
    async def append_to_note(self, path: str, content: str) -> None: ...
    async def delete_note(self, path: str) -> None: ...
    async def note_exists(self, path: str) -> bool: ...
    async def search_simple(self, query: str, context_length: int = 100) -> list[dict[str, Any]]: ...
    # ... remaining methods
```

### Pattern 2: Graceful Degradation for CLI Features

**What:** Some CLI commands may not have direct equivalents to all REST API features (e.g., JsonLogic search, DQL queries which depend on Dataview plugin). Design for graceful fallback.
**When:** Implementing CLIClient methods that may not have CLI equivalents

```python
async def search_jsonlogic(self, query: dict) -> list[dict[str, Any]]:
    """JsonLogic search -- may not be available via CLI."""
    raise NotImplementedError(
        "JsonLogic search requires the Obsidian REST API plugin. "
        "Use search_simple() for CLI-based search."
    )
```

### Pattern 3: CLI Output Parsing Isolation

**What:** Keep all CLI stdout/stderr parsing in dedicated parser functions, not scattered through client methods.
**When:** Building CLIClient

```python
# cli_parsers.py
def parse_note_output(stdout: str) -> dict[str, Any]:
    """Parse obsidian-cli vault read output into note dict."""
    ...

def parse_file_list(stdout: str) -> list[dict[str, str]]:
    """Parse obsidian-cli vault list output into file entries."""
    ...
```

### Pattern 4: Environment-Based Client Selection

**What:** Use environment variables to control which client backend is used
**When:** During migration period when both REST and CLI are supported

```python
# OBSIDIAN_BACKEND=cli (default) or OBSIDIAN_BACKEND=rest (legacy)
BACKEND = os.getenv("OBSIDIAN_BACKEND", "cli")
```

## Scalability Considerations

| Concern | At 100 notes | At 1K notes | At 10K+ notes |
|---------|-------------|-------------|---------------|
| Cache refresh | < 1s, no issue | 2-5s, acceptable | 10-30s, needs progress feedback or incremental refresh |
| CLI subprocess overhead | Negligible | Noticeable if many sequential calls | Consider batching or keeping connection open |
| Headless startup | 2-3s one-time | Same | Same, but memory usage of Obsidian grows |
| Memory folder size | Trivial | Trivial | May need subfolder organization |
| Backlink index build | Instant | < 1s | 5-10s, consider lazy computation |

## Build Order (Dependency Chain)

The components have clear dependencies that dictate build order:

```
1. VaultClient Protocol          (no dependencies, defines interface)
     |
2. ObsidianCLIClient            (depends on: Protocol, CLI binary)
     |
3. HeadlessManager              (depends on: Obsidian binary)
     |
4. CLI Client integration tests (depends on: CLIClient + HeadlessManager)
     |
5. Tool handler migration       (depends on: working CLIClient)
     |  - Update imports in tools/*.py
     |  - Add client factory function
     |  - Test each tool handler with CLI backend
     |
6. Claude Code Plugin           (depends on: working MCP server with CLI backend)
     |  - CLAUDE.md with auto-detection rules
     |  - Hook scripts
     |  - Slash commands
     |
7. Agent memory enhancements    (depends on: working Plugin + MCP server)
     - Dedicated memory folder conventions
     - Vault structure learning
     - Self-memory (how to navigate this vault)
```

**Phase ordering rationale:**
- Steps 1-3 are the backend swap -- must come first because everything else depends on CLI access working
- Step 4 validates the swap before migrating tool handlers
- Step 5 is mechanical (import changes) once CLIClient is proven
- Step 6 (plugin) requires a working MCP server but is otherwise independent of memory enhancements
- Step 7 builds on both the plugin (auto-detection) and MCP server (vault tools)

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| CLIClient mirrors ObsidianClient interface exactly | Minimizes tool handler changes, enables fallback |
| HeadlessManager owned by CLIClient, not global | Lifecycle tied to client session, avoids zombie processes |
| Plugin is a separate directory, not inside `src/` | Different runtime context (Claude Code vs MCP server), different language (shell/markdown vs Python) |
| Plugin communicates through MCP tools, never directly | Single access path, cache consistency, proper formatting |
| Factory function for client selection | Backward compatibility during migration, easy testing |
| All agent state in vault, never in external files | Vault is the single source of truth, portable, visible in Obsidian |

## Sources

- Existing codebase analysis: `src/obsidian_brain/client.py`, `server.py`, `cache.py`, `memory.py`, `models.py`, `onboarding.py`, `tools/vault.py`
- `SPECIFICATION.md` -- original technical spec for the REST API version
- `.planning/PROJECT.md` -- project context and requirements
- Training data knowledge of Obsidian CLI (LOW confidence -- could not verify with official docs, web access denied)
- Training data knowledge of Claude Code plugin conventions (LOW confidence -- could not verify with official docs, web access denied)

**Important caveat:** The Obsidian CLI command syntax and Claude Code plugin hook conventions described here are based on training data and may be outdated or incorrect. Phase-specific research should verify the exact CLI commands available in Obsidian 1.8+ and the current Claude Code plugin API before implementation begins.
