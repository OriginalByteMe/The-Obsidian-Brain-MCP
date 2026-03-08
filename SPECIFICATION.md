# The Obsidian Brain MCP - Technical Specification

> **Version**: 0.2.0
> **Status**: Active
> **Last Updated**: 2026-03-08

## Overview

An MCP (Model Context Protocol) server that uses the [Obsidian CLI](https://obsidian.md/) to enable AI agents to intelligently interact with Obsidian vaults. The server provides structured access to vault contents, semantic understanding of note relationships, and tools for research synthesis and daily note management.

### Primary Use Cases

1. **Research Synthesis**: Create well-linked notes from research with proper backlinks and tags
2. **Daily Note Management**: Capture information to daily notes with structured formatting
3. **Knowledge Traversal**: Navigate the vault's link graph to explore connected concepts

---

## Architecture

The server uses a CLI subprocess backend -- all vault operations are performed by invoking the `obsidian` CLI binary via `asyncio.create_subprocess_exec`. There is no REST API, no HTTP client, and no Docker deployment.

```
obsidian-brain-mcp/
src/
  obsidian_brain/
    __init__.py
    server.py              # FastMCP server definition and tool registration
    protocol.py            # VaultClient Protocol (abstract interface)
    cli_client.py          # ObsidianCLIClient (CLI subprocess implementation)
    parsers.py             # JSON/text output parsers for CLI responses
    exceptions.py          # CLI-specific exception hierarchy
    models.py              # Pydantic models for data structures
    cache.py               # In-memory vault structure cache
    tools/
      __init__.py
      vault.py             # Vault file operations
      links.py             # Backlink and traversal operations
      tags.py              # Tag management
      search.py            # Search operations (text search only)
      daily.py             # Daily note operations
      knowledge.py         # Knowledge base generation
      onboarding.py        # Vault analysis and configuration
      memory.py            # Cross-session persistent memory
    resources/
      __init__.py
      structure.py         # vault://structure resource
    utils/
      __init__.py
      wikilinks.py         # [[wikilink]] parsing and injection
      frontmatter.py       # YAML frontmatter manipulation
tests/
  ...
pyproject.toml
SPECIFICATION.md
README.md
```

### Backend: Obsidian CLI

All vault operations go through the `ObsidianCLIClient`, which implements the `VaultClient` Protocol. The CLI binary is located via `shutil.which("obsidian")` with an `OBSIDIAN_CLI_PATH` environment variable override.

**Key design decisions:**
- **No shell=True**: All subprocess calls use list-form arguments for safety
- **Explicit timeouts**: Every CLI call has a timeout to prevent hangs
- **Path sanitization**: Null byte rejection + structural safety from list-form exec
- **Singleton client**: One `ObsidianCLIClient` instance shared across all tools

### VaultClient Protocol

The `VaultClient` Protocol defines the async interface for vault operations. It uses structural typing (`typing.Protocol` with `@runtime_checkable`) so implementations satisfy the protocol by having matching method signatures -- no inheritance required.

```python
@runtime_checkable
class VaultClient(Protocol):
    async def list_directory(self, path: str = "/") -> list[dict[str, Any]]: ...
    async def get_all_files(self, path: str = "/") -> list[str]: ...
    async def get_note(self, path: str, include_metadata: bool = True) -> dict[str, Any]: ...
    async def note_exists(self, path: str) -> bool: ...
    async def create_note(self, path: str, content: str) -> None: ...
    async def update_note(self, path: str, content: str) -> None: ...
    async def append_to_note(self, path: str, content: str) -> None: ...
    async def delete_note(self, path: str) -> None: ...
    async def search_simple(self, query: str, context_length: int = 100) -> list[dict[str, Any]]: ...
    async def get_daily_note(self, date: str | None = None) -> dict[str, Any]: ...
    async def append_daily(self, content: str, date: str | None = None) -> None: ...
    async def get_tags(self) -> dict[str, int]: ...
    async def get_backlinks(self, path: str) -> list[str]: ...
    async def get_links(self, path: str) -> list[str]: ...
```

### CLI Command Mapping

| VaultClient Method | CLI Command |
|---|---|
| `list_directory` | `obsidian files folder="{path}" format=json` |
| `get_all_files` | `obsidian files ext=md format=json` |
| `get_note` | `obsidian read path="{path}" format=json` |
| `note_exists` | `obsidian read` (check returncode) |
| `create_note` | `obsidian create name="{name}" path="{folder}" content="{content}" --silent` |
| `update_note` | `obsidian create --overwrite --silent` |
| `append_to_note` | `obsidian append file="{name}" content="{content}"` |
| `delete_note` | `obsidian delete file="{name}"` |
| `search_simple` | `obsidian search query="{query}" format=json` |
| `get_daily_note` | `obsidian daily:read format=json` |
| `append_daily` | `obsidian daily:append content="{content}"` |
| `get_tags` | `obsidian tags format=json` |
| `get_backlinks` | `obsidian backlinks file="{name}" format=json` |
| `get_links` | `obsidian links file="{name}" format=json` |

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OBSIDIAN_CLI_PATH` | No | auto-detected | Path to Obsidian CLI binary |

The `obsidian` CLI binary must be available on PATH or specified via `OBSIDIAN_CLI_PATH`. Requires Obsidian 1.12.4+ with CLI enabled in Settings > General.

---

## Data Models

### VaultStructure

The cached representation of the entire vault, exposed via the `vault://structure` resource.

```python
class FolderNode(BaseModel):
    name: str
    path: str  # e.g., "Projects/Active/"
    children: list["FolderNode"] = []

class NoteMetadata(BaseModel):
    path: str                      # e.g., "Projects/Active/MyProject.md"
    title: str                     # Auto-extracted from filename or H1
    tags: list[str] = []
    outgoing_links: list[str] = []
    incoming_links: list[str] = []
    frontmatter: dict = {}
    modified: datetime | None

class VaultStats(BaseModel):
    total_notes: int
    total_folders: int
    total_tags: int
    total_links: int
    orphan_notes: int

class VaultStructure(BaseModel):
    folders: list[FolderNode]
    notes: list[NoteMetadata]
    stats: VaultStats
    refreshed_at: datetime
```

---

## Caching Strategy

The `VaultCache` provides an in-memory cache of vault structure with on-demand refresh.

**Cache refresh is optimized for CLI performance:**
1. **Bulk file listing**: Single `get_all_files()` call (maps to `obsidian files ext=md format=json`) instead of recursive directory traversal
2. **Bounded concurrent reads**: Note metadata is fetched with `asyncio.Semaphore(10)` -- up to 10 notes read concurrently via `asyncio.gather`
3. **Folder hierarchy derived**: Built from flat file paths rather than recursive `list_directory` calls
4. **Backlink index computed cache-side**: Uses extracted wikilinks from note content, not CLI backlinks command (avoids N+1 CLI calls)

```python
class VaultCache:
    async def refresh(self, client: VaultClient) -> VaultStructure: ...
    def get_structure(self) -> VaultStructure: ...
    def get_backlinks(self, path: str) -> list[str]: ...
    def get_note_metadata(self, path: str) -> NoteMetadata | None: ...
    def get_all_tags(self) -> dict[str, int]: ...
    def get_notes_by_tag(self, tag: str) -> list[str]: ...
    def invalidate_path(self, path: str) -> None: ...
```

---

## Error Handling

### Exception Hierarchy

```python
class ObsidianCLIError(Exception):
    """Base exception for CLI execution failures."""

class NoteNotFoundError(ObsidianCLIError):
    """Raised when a note doesn't exist."""

class CLITimeoutError(ObsidianCLIError):
    """Raised when CLI command exceeds timeout."""

class CLINotFoundError(Exception):
    """Raised when obsidian binary is not found (not a subclass of ObsidianCLIError)."""

class CacheNotInitializedError(Exception):
    """Raised when cache is accessed before initialization."""
```

---

## MCP Server

The server uses **FastMCP** from the official `mcp` SDK (>= 1.26.0). Tools are registered via `register_*_tools(server, client)` functions in each tool module.

```python
from mcp.server.fastmcp import FastMCP

server = FastMCP("obsidian-brain")
client = ObsidianCLIClient()

register_vault_tools(server, client)
register_link_tools(server, client)
register_tag_tools(server, client)
# ... etc
```

### Tools Removed from REST Version

The following tools had no CLI equivalent and were removed:
- `search_advanced` (Dataview DQL queries)
- `search_jsonlogic` (JsonLogic queries)
- `get_periodic_note` (weekly/monthly/quarterly/yearly notes)

---

## Security Considerations

1. **No shell injection**: All subprocess calls use list-form arguments (never `shell=True`)
2. **Path sanitization**: Null byte rejection prevents path injection
3. **Explicit timeouts**: All CLI calls have bounded execution time
4. **No secrets in env**: No API keys required (CLI uses local Obsidian instance)

---

## Dependencies

```toml
dependencies = [
    "mcp>=1.26.0",
    "pydantic>=2.0.0",
    "python-frontmatter>=1.1.0",
]
```

No HTTP client libraries. No Docker deployment.
