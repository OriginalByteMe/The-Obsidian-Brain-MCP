# The Obsidian Brain MCP - Technical Specification

> **Version**: 0.2.0
> **Status**: Active
> **Last Updated**: 2026-07-26

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
    parsers.py             # Text-output parsers for CLI responses
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
      knowledge.py         # vault://knowledge resource
      notes.py             # vault://files index and vault://note/{path} template
      structure.py         # vault://structure, vault://tags, vault://stats resources
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

All vault operations go through the `ObsidianCLIClient`, which implements the `VaultClient` Protocol. The CLI binary is located via `shutil.which("obsidian")` with an `OBSIDIAN_CLI_PATH` environment variable override; `OBSIDIAN_VAULT` optionally selects a vault by folder name or id.

**CLI registration:** In Obsidian, open **Settings > General > Advanced**, turn **Command line interface** on, and accept the follow-up prompt to register it in your PATH. On Linux this copies Obsidian's bundled `obsidian-cli` to `~/.local/bin/obsidian` (mode 755); `~/.local/bin` must be on `PATH`. On Windows it appends the install directory to the user PATH; on macOS it links into `/usr/local/bin`. Verify with `obsidian version` (for example, `1.12.7 (installer 1.12.7)`).

**Vault resolution:** The CLI checks, in order: (1) the `vault=` argument sent by this server when `OBSIDIAN_VAULT` is set; (2) the calling process's CWD if it is inside a registered vault; (3) the most recently focused open vault window; and (4) otherwise fails with `Vault not found.`. If `OBSIDIAN_VAULT` is unset, the vault must be open in Obsidian. Setting it to the vault's folder name or its id from `~/.config/obsidian/obsidian.json` is reliable, and Obsidian opens that vault's window on demand.

**Key design decisions:**
- **No shell=True**: All subprocess calls use list-form arguments for safety
- **Explicit timeouts**: Every CLI call has a timeout to bound subprocess lifetime
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
    async def create_note(self, path: str, content: str) -> str: ...  # returns the actual created path
    async def update_note(self, path: str, content: str) -> None: ...
    async def append_to_note(self, path: str, content: str) -> None: ...
    async def delete_note(self, path: str) -> None: ...
    async def search_simple(self, query: str) -> list[dict[str, Any]]: ...
    async def get_daily_note(self, date: str | None = None) -> dict[str, Any]: ...
    async def append_daily(self, content: str, date: str | None = None) -> None: ...
```

### CLI Command Mapping

| VaultClient Method | CLI Command |
|---|---|
| `list_directory` | `obsidian files [folder="{path}"]` (recursive; never returns folders) |
| `get_all_files` | `obsidian files [folder="{path}"]` (recursive; never returns folders) |
| `get_note` | `obsidian read path="{path}"` |
| `note_exists` | `obsidian read path="{path}"` (check return code) |
| `create_note` | `obsidian create path="{path}" content="{content}"` |
| `update_note` | `obsidian create path="{path}" content="{content}" overwrite` |
| `append_to_note` | `obsidian append path="{path}" content="{content}"` |
| `delete_note` | `obsidian delete path="{path}"` |
| `search_simple` | `obsidian search:context query="{query}" format=text` |
| `get_daily_note` | `obsidian daily:read [date="{date}"]` |
| `append_daily` | `obsidian daily:append content="{content}" [date="{date}"]` |

`search_simple` accepts only the query and always uses `search:context format=text`;
the CLI exposes no context-length option. `ObsidianCLIClient` parses the text
output directly and has no JSON execution helper or `parse_tags` /
`parse_file_list` compatibility parsers.

`get_note` returns `path`, parsed Markdown `content`, normalized `tags`,
remaining `frontmatter`, `modified`, and `raw`. The `raw` value is the complete
original document, including YAML frontmatter (and equals `content` when no
frontmatter is present). Frontmatter is parsed by the installed
`python-frontmatter` dependency rather than a hand-written YAML parser.

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OBSIDIAN_CLI_PATH` | No | auto-detected | Executable path when `obsidian` is not on `PATH`; set it to point at the binary explicitly |
| `OBSIDIAN_VAULT` | No | see vault resolution above | Vault folder name or id (not a filesystem path), passed as the CLI's `vault=` argument |

The registered CLI requires the Obsidian desktop app to be running. See the registration and vault-resolution rules above. Onboarding writes the vault profile to `Obsidian Brain/config.md` (fenced YAML in a Markdown note): the CLI's `create` command forces the `.md` extension and cannot write into dot-folders, so a `.yml` or `.obsidian-brain/` target can never exist.

---

## Data Models

### VaultStructure

The cached, note-oriented representation of the vault, exposed via the `vault://structure` resource.

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

The cache separately retains every vault file path for `vault://files`; attachments are not represented as `NoteMetadata`.

---

## Caching Strategy

The `VaultCache` provides an in-memory cache populated on demand by `refresh_vault_structure`.

**Cache refresh is optimized for CLI performance:**
1. **Bulk file listing**: Single `get_all_files()` call (maps to `obsidian files`) returns every vault file
2. **Markdown-only metadata reads**: Attachments stay in the all-file index, while Markdown note metadata is fetched with `asyncio.Semaphore(10)` and `asyncio.gather`
3. **Folder hierarchy derived**: Built from flat file paths rather than recursive `list_directory` calls
4. **Backlink index computed cache-side**: Uses extracted wikilinks from note content, not CLI backlinks command (avoids N+1 CLI calls)

```python
class VaultCache:
    async def refresh(self, client: VaultClient) -> VaultStructure: ...
    def get_structure(self) -> VaultStructure: ...
    def get_file_paths(self) -> list[str]: ...
    def get_backlinks(self, path: str) -> list[str]: ...
    def get_note_metadata(self, path: str) -> NoteMetadata | None: ...
    def get_all_tags(self) -> dict[str, int]: ...
    def get_notes_by_tag(self, tag: str) -> list[str]: ...
    def invalidate_path(self, path: str) -> None: ...
```

---

## Error Handling

### CLI Error Reporting

Application-level failures are reported as a line of STDOUT with exit code 0 (for example, `Vault not found.` or `Error: File "X" not found.`). The exception is the CLI binary failing to reach Obsidian: it exits 1 and writes `The CLI is unable to find Obsidian. Please make sure Obsidian is running and try again.` to STDERR. The server also classifies other non-zero exits or STDERR text as failures.

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

The server uses **FastMCP** from the official `mcp` Python SDK v1 line (`>=1.26.0,<2`). Tools are registered via `register_*_tools(server, client)` functions in each tool module.

```python
from mcp.server.fastmcp import FastMCP

server = FastMCP("obsidian-brain")
client = ObsidianCLIClient()

register_vault_tools(server, client)
register_link_tools(server, client)
register_tag_tools(server, client)
# ... etc
```

Run a local checkout through the package module:

```bash
uv run python -m obsidian_brain.server
```

### Resources

| Resource | Description |
|---|---|
| `vault://files` | Cached JSON index of every vault file |
| `vault://note/{path}` | Markdown reader template for readable entries in `vault://files` |
| `vault://structure` | Cached folder hierarchy and Markdown note metadata |
| `vault://tags` | Cached tag counts |
| `vault://stats` | Cached aggregate vault statistics |
| `vault://knowledge` | Persistent Markdown knowledge base |

`refresh_vault_structure` populates the cached structure. Each `vault://files` entry has `path`, lowercase `extension`, and `readable`; readable Markdown entries also have a percent-encoded `vault://note/{path}` URI, while attachments do not. MCP resource discovery and reads are the server-side guarantee. IDE `@` pickers are host features, so the server cannot force resources into or customize them.

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
    "mcp>=1.26.0,<2",
    "pydantic>=2.0.0",
    "python-frontmatter>=1.1.0",
]
```

The project stays on the stable, supported v1 line of the official MCP Python SDK. MCP v2 is still alpha, and standalone `fastmcp` v4 requires the `mcp==2.0.0b2` prerelease.

No HTTP client libraries. No Docker deployment.
