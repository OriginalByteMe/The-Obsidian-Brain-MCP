# The Obsidian Brain MCP - Technical Specification

> **Version**: 0.1.0
> **Status**: Draft
> **Last Updated**: 2025-01-06

## Overview

An MCP (Model Context Protocol) server that wraps the [Obsidian Local REST API](https://coddingtonbear.github.io/obsidian-local-rest-api/), enabling AI agents to intelligently interact with Obsidian vaults. The server provides structured access to vault contents, semantic understanding of note relationships, and tools for research synthesis and daily note management.

### Primary Use Cases

1. **Research Synthesis**: Create well-linked notes from research with proper backlinks and tags
2. **Daily Note Management**: Capture information to daily notes with structured formatting
3. **Knowledge Traversal**: Navigate the vault's link graph to explore connected concepts

---

## Architecture

```
obsidian-brain-mcp/
├── src/
│   └── obsidian_brain/
│       ├── __init__.py
│       ├── server.py              # MCPServer definition and registration
│       ├── client.py              # ObsidianClient (async httpx wrapper)
│       ├── models.py              # Pydantic models for data structures
│       ├── cache.py               # In-memory vault structure cache
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── vault.py           # Vault file operations
│       │   ├── links.py           # Backlink and traversal operations
│       │   ├── tags.py            # Tag management
│       │   ├── search.py          # Search operations
│       │   └── daily.py           # Daily/periodic note operations
│       ├── resources/
│       │   ├── __init__.py
│       │   └── structure.py       # vault://structure resource
│       └── utils/
│           ├── __init__.py
│           ├── wikilinks.py       # [[wikilink]] parsing and injection
│           └── frontmatter.py     # YAML frontmatter manipulation
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_client.py
│   ├── test_tools/
│   └── test_utils/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── SPECIFICATION.md
└── README.md
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OBSIDIAN_API_KEY` | Yes | - | Bearer token from Obsidian Local REST API plugin |
| `OBSIDIAN_HOST` | No | `127.0.0.1` | Obsidian API host |
| `OBSIDIAN_PORT` | No | `27124` | Obsidian API port |
| `OBSIDIAN_VERIFY_SSL` | No | `false` | Verify SSL certificate (self-signed by default) |
| `DAILY_NOTE_TEMPLATE` | No | `templates/daily.md` | Path to daily note template in vault |

### Example `.env`

```bash
OBSIDIAN_API_KEY=your_api_key_here
OBSIDIAN_HOST=127.0.0.1
OBSIDIAN_PORT=27124
OBSIDIAN_VERIFY_SSL=false
DAILY_NOTE_TEMPLATE=templates/daily.md
```

---

## Data Models

### VaultStructure

The cached representation of the entire vault, exposed via the `vault://structure` resource.

```python
class FolderNode(BaseModel):
    """Represents a folder in the vault hierarchy"""
    name: str
    path: str  # Relative path from vault root, e.g., "Projects/Active/"
    children: list["FolderNode"] = []

class NoteMetadata(BaseModel):
    """Metadata for a single note"""
    path: str                      # e.g., "Projects/Active/MyProject.md"
    title: str                     # Auto-extracted from filename or H1
    tags: list[str] = []           # From frontmatter
    outgoing_links: list[str] = [] # [[wikilinks]] this note contains
    incoming_links: list[str] = [] # Notes that link TO this note (backlinks)
    frontmatter: dict = {}         # Full frontmatter as dict
    modified: datetime | None      # Last modified timestamp

class VaultStats(BaseModel):
    """Aggregate statistics about the vault"""
    total_notes: int
    total_folders: int
    total_tags: int
    total_links: int
    orphan_notes: int  # Notes with no incoming or outgoing links

class VaultStructure(BaseModel):
    """Complete vault structure for caching"""
    folders: list[FolderNode]
    notes: list[NoteMetadata]
    stats: VaultStats
    refreshed_at: datetime
```

### JSON Schema (for resource response)

```json
{
    "folders": [
        {
            "name": "Projects",
            "path": "Projects/",
            "children": [
                {"name": "Active", "path": "Projects/Active/", "children": []}
            ]
        }
    ],
    "notes": [
        {
            "path": "Projects/Active/MyProject.md",
            "title": "MyProject",
            "tags": ["project", "active"],
            "outgoing_links": ["[[Reference Note]]", "[[Meeting Notes]]"],
            "incoming_links": ["[[Index]]", "[[Daily/2024-01-15]]"],
            "frontmatter": {"status": "in-progress", "created": "2024-01-10"},
            "modified": "2024-01-15T10:30:00Z"
        }
    ],
    "stats": {
        "total_notes": 342,
        "total_folders": 28,
        "total_tags": 67,
        "total_links": 1205,
        "orphan_notes": 12
    },
    "refreshed_at": "2024-01-15T14:22:00Z"
}
```

---

## ObsidianClient

Async HTTP client wrapping the Obsidian Local REST API.

### Class Definition

```python
class ObsidianClient:
    """
    Async wrapper for Obsidian Local REST API.

    Handles authentication, SSL verification, and response parsing.
    """

    def __init__(
        self,
        api_key: str,
        host: str = "127.0.0.1",
        port: int = 27124,
        verify_ssl: bool = False
    ):
        self.base_url = f"https://{host}:{port}"
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ObsidianClient": ...
    async def __aexit__(self, *args) -> None: ...
```

### Methods

#### Directory Operations

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `list_directory` | `path: str = "/"` | `list[dict]` | List files and folders at path |
| `get_all_files` | `path: str = "/"` | `list[str]` | Recursively get all file paths |

#### Note Operations

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `get_note` | `path: str, include_metadata: bool = True` | `dict` | Get note content and optional metadata |
| `create_note` | `path: str, content: str` | `None` | Create new note (PUT) |
| `update_note` | `path: str, content: str` | `None` | Replace note content (PUT) |
| `append_to_note` | `path: str, content: str` | `None` | Append to note (POST) |
| `patch_note` | `path: str, operation: str, content: str, target_type: str = None, target: str = None` | `None` | Partial update (PATCH) |
| `delete_note` | `path: str` | `None` | Delete note (DELETE) |
| `note_exists` | `path: str` | `bool` | Check if note exists |

#### Search Operations

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `search_simple` | `query: str, context_length: int = 100` | `list[dict]` | Full-text search with snippets |
| `search_dql` | `query: str` | `list[dict]` | Dataview DQL query |
| `search_jsonlogic` | `query: dict` | `list[dict]` | JsonLogic query |

#### Periodic Notes

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `get_periodic` | `period: str = "daily", date: str = None` | `dict` | Get periodic note |
| `append_periodic` | `content: str, period: str = "daily", date: str = None` | `None` | Append to periodic note |
| `update_periodic` | `content: str, period: str = "daily", date: str = None` | `None` | Update periodic note |

### Request Headers

```python
def _get_headers(self, accept_json: bool = False) -> dict:
    headers = {
        "Authorization": f"Bearer {self.api_key}",
    }
    if accept_json:
        headers["Accept"] = "application/vnd.olrapi.note+json"
    else:
        headers["Accept"] = "text/markdown"
    return headers
```

---

## MCP Resources

### `vault://structure`

**Type**: Read-only cached resource
**MIME Type**: `application/json`
**Refresh**: On-demand via `refresh_vault_structure` tool

```python
@server.resource(uri="vault://structure", mime_type="application/json")
async def vault_structure() -> str:
    """
    Returns the cached vault structure including folders, notes with metadata,
    and aggregate statistics. Use refresh_vault_structure tool to update.
    """
    structure = await cache.get_structure()
    return structure.model_dump_json()
```

---

## MCP Tools

### Vault Operations

#### `list_vault_files`

List files and folders at a specified path.

```python
@server.tool()
async def list_vault_files(path: str = "/") -> str:
    """
    List all files and folders at the specified vault path.

    Args:
        path: Relative path in vault (default: root "/")

    Returns:
        JSON array of file/folder entries with names and types
    """
```

**Example Response**:
```json
[
    {"name": "Projects", "type": "folder"},
    {"name": "Index.md", "type": "file"},
    {"name": "README.md", "type": "file"}
]
```

---

#### `get_note`

Retrieve a note's content and metadata.

```python
@server.tool()
async def get_note(path: str) -> str:
    """
    Get the content and metadata of a specific note.

    Args:
        path: Path to the note (e.g., "Projects/MyProject.md")

    Returns:
        JSON with content, tags, links, and frontmatter
    """
```

**Example Response**:
```json
{
    "path": "Projects/MyProject.md",
    "content": "# MyProject\n\nProject description...",
    "tags": ["project", "active"],
    "outgoing_links": ["[[Reference]]"],
    "frontmatter": {"status": "active"},
    "modified": "2024-01-15T10:30:00Z"
}
```

---

#### `create_note`

Create a new note with auto-generated header, frontmatter tags, and backlinks.

```python
@server.tool()
async def create_note(
    path: str,
    content: str,
    tags: list[str] = [],
    backlinks: list[str] = []
) -> str:
    """
    Create a new note with frontmatter tags and wikilinks.

    The title is auto-generated from the filename. Backlinks are validated
    to ensure target notes exist before being added.

    Args:
        path: Path for new note (e.g., "Research/AI Safety.md")
        content: Main content body (without frontmatter or title)
        tags: List of tags to add to frontmatter
        backlinks: List of note names to link to (validated for existence)

    Returns:
        Confirmation message with created note path

    Raises:
        ValueError: If any backlink target does not exist
    """
```

**Generated Note Structure**:
```markdown
---
tags:
  - research
  - ai-safety
created: 2024-01-15
---

# AI Safety

[User-provided content here]

## See Also

- [[Related Note 1]]
- [[Related Note 2]]
```

---

#### `update_note`

Replace a note's entire content.

```python
@server.tool()
async def update_note(path: str, content: str) -> str:
    """
    Replace the entire content of an existing note.

    Args:
        path: Path to the note
        content: New content (replaces everything)

    Returns:
        Confirmation message
    """
```

---

#### `append_to_note`

Append content to a note, optionally under a specific heading.

```python
@server.tool()
async def append_to_note(
    path: str,
    content: str,
    heading: str | None = None
) -> str:
    """
    Append content to an existing note.

    Args:
        path: Path to the note
        content: Content to append
        heading: Optional heading to append under (e.g., "## Notes")
                 If heading doesn't exist, it will be created

    Returns:
        Confirmation message
    """
```

---

### Link Operations

#### `add_backlink`

Add a wikilink from one note to another.

```python
@server.tool()
async def add_backlink(
    source_path: str,
    target_note: str,
    context: str = ""
) -> str:
    """
    Add a [[wikilink]] to target_note in the source note.

    The target note is validated to exist before adding the link.

    Args:
        source_path: Path to note where link will be added
        target_note: Name of note to link to (without .md extension)
        context: Optional context text before the link

    Returns:
        Confirmation message

    Raises:
        ValueError: If target_note does not exist in vault

    Example:
        add_backlink("Projects/AI.md", "Research/Papers", "See also")
        # Adds: "See also [[Research/Papers]]" to Projects/AI.md
    """
```

---

#### `get_backlinks`

Get all notes that link to a specific note.

```python
@server.tool()
async def get_backlinks(path: str) -> str:
    """
    Get all notes that contain links TO the specified note.

    Args:
        path: Path to the note

    Returns:
        JSON array of note paths that link to this note
    """
```

---

#### `get_outgoing_links`

Get all notes that a specific note links to.

```python
@server.tool()
async def get_outgoing_links(path: str) -> str:
    """
    Get all notes that the specified note links TO.

    Args:
        path: Path to the note

    Returns:
        JSON array of linked note paths
    """
```

---

#### `get_linked_notes`

Traverse the link graph from a starting note.

```python
@server.tool()
async def get_linked_notes(
    path: str,
    depth: int = 1,
    direction: str = "both"
) -> str:
    """
    Traverse the link graph starting from a note.

    Args:
        path: Starting note path
        depth: How many hops to traverse (1-3, default 1)
        direction: "incoming" (backlinks), "outgoing", or "both"

    Returns:
        JSON object with nodes and edges representing the subgraph
    """
```

**Example Response** (depth=1, direction="both"):
```json
{
    "center": "Projects/MyProject.md",
    "nodes": [
        {"path": "Projects/MyProject.md", "depth": 0},
        {"path": "Index.md", "depth": 1},
        {"path": "Research/Paper1.md", "depth": 1}
    ],
    "edges": [
        {"from": "Index.md", "to": "Projects/MyProject.md"},
        {"from": "Projects/MyProject.md", "to": "Research/Paper1.md"}
    ]
}
```

---

### Tag Operations

#### `add_tags`

Add tags to a note's frontmatter.

```python
@server.tool()
async def add_tags(path: str, tags: list[str]) -> str:
    """
    Add tags to a note's frontmatter.

    Existing tags are preserved; duplicates are ignored.

    Args:
        path: Path to the note
        tags: List of tags to add

    Returns:
        Confirmation with updated tag list
    """
```

---

#### `remove_tags`

Remove tags from a note's frontmatter.

```python
@server.tool()
async def remove_tags(path: str, tags: list[str]) -> str:
    """
    Remove tags from a note's frontmatter.

    Args:
        path: Path to the note
        tags: List of tags to remove

    Returns:
        Confirmation with updated tag list
    """
```

---

#### `list_all_tags`

Get the complete tag taxonomy across the vault.

```python
@server.tool()
async def list_all_tags() -> str:
    """
    Get all unique tags used across the vault with counts.

    Returns:
        JSON object mapping tag names to usage counts
    """
```

**Example Response**:
```json
{
    "project": 45,
    "research": 23,
    "daily": 180,
    "meeting": 34
}
```

---

#### `get_notes_by_tag`

Find all notes with a specific tag.

```python
@server.tool()
async def get_notes_by_tag(tag: str) -> str:
    """
    Get all notes that have a specific tag.

    Args:
        tag: Tag to search for (without #)

    Returns:
        JSON array of note paths with this tag
    """
```

---

### Search Operations

#### `search_content`

Full-text search across vault content.

```python
@server.tool()
async def search_content(
    query: str,
    context_length: int = 100
) -> str:
    """
    Search for text across all notes in the vault.

    Args:
        query: Search query string
        context_length: Characters of context around matches (default 100)

    Returns:
        JSON array of matches with file paths, snippets, and scores
    """
```

---

#### `search_advanced`

Execute a Dataview DQL query.

```python
@server.tool()
async def search_advanced(dql_query: str) -> str:
    """
    Execute a Dataview DQL query against the vault.

    Requires Dataview plugin to be installed in Obsidian.

    Args:
        dql_query: Dataview Query Language query string

    Returns:
        JSON array of matching results

    Example:
        search_advanced("TABLE file.ctime FROM #project WHERE status = 'active'")
    """
```

---

### Daily Note Operations

#### `get_daily_note`

Get today's or a specific date's daily note.

```python
@server.tool()
async def get_daily_note(date: str | None = None) -> str:
    """
    Get the daily note for today or a specific date.

    Args:
        date: Optional date in YYYY-MM-DD format (default: today)

    Returns:
        JSON with daily note content and metadata
    """
```

---

#### `append_to_daily`

Add content to today's daily note.

```python
@server.tool()
async def append_to_daily(
    content: str,
    heading: str | None = None
) -> str:
    """
    Append content to today's daily note.

    If the daily note doesn't exist, it will be created from template.

    Args:
        content: Content to append
        heading: Optional heading to append under (e.g., "## Notes")

    Returns:
        Confirmation message
    """
```

---

#### `create_daily_entry`

Create a structured entry in today's daily note.

```python
@server.tool()
async def create_daily_entry(
    content: str,
    tags: list[str] = [],
    links: list[str] = []
) -> str:
    """
    Create a structured entry in today's daily note.

    Entry format:
    - [timestamp] content [[links]] #tags

    Args:
        content: Entry text
        tags: Optional inline tags to add
        links: Optional wikilinks to include (validated)

    Returns:
        Confirmation message
    """
```

---

### Structure Management

#### `refresh_vault_structure`

Rebuild the cached vault structure.

```python
@server.tool()
async def refresh_vault_structure() -> str:
    """
    Rebuild the cached vault structure.

    This scans the entire vault and rebuilds the structure cache including
    all folder hierarchies, note metadata, backlinks, and statistics.

    This is a potentially slow operation for large vaults.

    Returns:
        Summary of refreshed structure (note count, folder count, etc.)
    """
```

---

## Utility Functions

### Wikilink Utilities (`utils/wikilinks.py`)

```python
import re

WIKILINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')

def extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wikilink]] targets from content."""
    return WIKILINK_PATTERN.findall(content)

def inject_wikilink(
    content: str,
    target: str,
    context: str = "",
    section: str = "See Also"
) -> str:
    """
    Inject a [[wikilink]] into content.

    Adds to existing "See Also" section or creates one.
    """
    link = f"[[{target}]]"
    if context:
        link = f"{context} {link}"

    # Check for existing section
    section_pattern = re.compile(rf'^## {section}\s*$', re.MULTILINE)
    if section_pattern.search(content):
        # Add under existing section
        return section_pattern.sub(f"## {section}\n\n- {link}", content, count=1)
    else:
        # Create new section at end
        return f"{content.rstrip()}\n\n## {section}\n\n- {link}\n"

def resolve_wikilink(link: str, current_path: str, all_notes: list[str]) -> str | None:
    """
    Resolve a wikilink to a full path.

    Handles:
    - Full paths: [[folder/note]]
    - Relative: [[note]] (searches vault)
    - Aliases: [[note|alias]]
    """
    # Implementation details...
```

### Frontmatter Utilities (`utils/frontmatter.py`)

```python
import frontmatter
from datetime import datetime

def parse_note(content: str) -> tuple[dict, str]:
    """Parse note into frontmatter dict and body content."""
    post = frontmatter.loads(content)
    return dict(post.metadata), post.content

def add_frontmatter_tags(content: str, tags: list[str]) -> str:
    """Add tags to note frontmatter, preserving existing."""
    post = frontmatter.loads(content)
    existing = post.get('tags', [])
    if isinstance(existing, str):
        existing = [existing]
    post['tags'] = sorted(set(existing + tags))
    return frontmatter.dumps(post)

def remove_frontmatter_tags(content: str, tags: list[str]) -> str:
    """Remove tags from note frontmatter."""
    post = frontmatter.loads(content)
    existing = post.get('tags', [])
    if isinstance(existing, str):
        existing = [existing]
    post['tags'] = [t for t in existing if t not in tags]
    return frontmatter.dumps(post)

def create_note_with_frontmatter(
    title: str,
    content: str,
    tags: list[str] = [],
    extra_frontmatter: dict = {}
) -> str:
    """
    Create a new note with proper frontmatter and title.

    Returns complete note content ready for saving.
    """
    fm = {
        'tags': tags,
        'created': datetime.now().strftime('%Y-%m-%d'),
        **extra_frontmatter
    }
    post = frontmatter.Post(f"# {title}\n\n{content}", **fm)
    return frontmatter.dumps(post)
```

---

## Caching Strategy

### Cache Implementation (`cache.py`)

```python
from datetime import datetime
from models import VaultStructure

class VaultCache:
    """In-memory cache for vault structure with on-demand refresh."""

    def __init__(self):
        self._structure: VaultStructure | None = None
        self._lock = asyncio.Lock()

    async def get_structure(self) -> VaultStructure:
        """Get cached structure, raises if not initialized."""
        if self._structure is None:
            raise ValueError("Vault structure not initialized. Call refresh first.")
        return self._structure

    async def refresh(self, client: ObsidianClient) -> VaultStructure:
        """Rebuild structure from vault."""
        async with self._lock:
            # 1. Recursively list all files
            # 2. Fetch metadata for each note
            # 3. Extract wikilinks from content
            # 4. Build backlink index
            # 5. Compute statistics
            self._structure = await self._build_structure(client)
            return self._structure

    async def _build_structure(self, client: ObsidianClient) -> VaultStructure:
        """Internal method to build complete structure."""
        # Implementation...

# Global singleton
cache = VaultCache()
```

### Backlink Index Building

```python
async def _build_backlink_index(
    notes: list[NoteMetadata]
) -> dict[str, list[str]]:
    """
    Build reverse index of backlinks.

    Returns dict mapping note path -> list of paths that link to it.
    """
    index: dict[str, list[str]] = {}

    for note in notes:
        for link in note.outgoing_links:
            resolved = resolve_wikilink(link, note.path, [n.path for n in notes])
            if resolved:
                if resolved not in index:
                    index[resolved] = []
                index[resolved].append(note.path)

    return index
```

---

## Error Handling

### Custom Exceptions

```python
class ObsidianBrainError(Exception):
    """Base exception for Obsidian Brain MCP."""
    pass

class NoteNotFoundError(ObsidianBrainError):
    """Raised when a note doesn't exist."""
    pass

class InvalidBacklinkError(ObsidianBrainError):
    """Raised when backlink target doesn't exist."""
    pass

class ObsidianAPIError(ObsidianBrainError):
    """Raised when Obsidian API returns an error."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Obsidian API error ({status_code}): {message}")

class CacheNotInitializedError(ObsidianBrainError):
    """Raised when cache is accessed before initialization."""
    pass
```

### Error Responses

All tools return consistent error format:

```json
{
    "error": true,
    "type": "NoteNotFoundError",
    "message": "Note not found: Projects/NonExistent.md"
}
```

---

## Docker Configuration

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy source code
COPY src/ ./src/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Run the server
CMD ["uv", "run", "python", "-m", "obsidian_brain.server"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  obsidian-brain:
    build: .
    container_name: obsidian-brain-mcp
    environment:
      - OBSIDIAN_API_KEY=${OBSIDIAN_API_KEY}
      - OBSIDIAN_HOST=${OBSIDIAN_HOST:-host.docker.internal}
      - OBSIDIAN_PORT=${OBSIDIAN_PORT:-27124}
      - OBSIDIAN_VERIFY_SSL=${OBSIDIAN_VERIFY_SSL:-false}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    stdin_open: true
    tty: true
    restart: unless-stopped
```

### Running with Docker

```bash
# Build
docker-compose build

# Run (stdio mode for MCP)
docker-compose run --rm obsidian-brain

# Or run detached for testing
docker-compose up -d
```

---

## MCP Client Configuration

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "obsidian-brain": {
      "command": "docker",
      "args": [
        "compose",
        "-f", "/path/to/obsidian-brain-mcp/docker-compose.yml",
        "run", "--rm", "obsidian-brain"
      ],
      "env": {
        "OBSIDIAN_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### Alternative: Direct Python

```json
{
  "mcpServers": {
    "obsidian-brain": {
      "command": "uv",
      "args": ["run", "python", "-m", "obsidian_brain.server"],
      "cwd": "/path/to/obsidian-brain-mcp",
      "env": {
        "OBSIDIAN_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

---

## Dependencies

### pyproject.toml

```toml
[project]
name = "obsidian-brain-mcp"
version = "0.1.0"
description = "MCP server for intelligent Obsidian vault interaction"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "mcp-use>=1.5.1",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
    "python-frontmatter>=1.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-httpx>=0.30.0",
    "ruff>=0.4.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (MVP)
- [ ] ObsidianClient with basic CRUD operations
- [ ] Vault structure cache with manual refresh
- [ ] `vault://structure` resource
- [ ] Tools: `list_vault_files`, `get_note`, `create_note`, `update_note`
- [ ] Tools: `refresh_vault_structure`
- [ ] Basic error handling
- [ ] Docker configuration

### Phase 2: Links & Tags
- [ ] Wikilink parsing utilities
- [ ] Frontmatter manipulation utilities
- [ ] Tools: `add_backlink`, `get_backlinks`, `get_outgoing_links`
- [ ] Tools: `add_tags`, `remove_tags`, `list_all_tags`, `get_notes_by_tag`
- [ ] Backlink validation

### Phase 3: Search & Daily Notes
- [ ] Tools: `search_content`, `search_advanced`
- [ ] Tools: `get_daily_note`, `append_to_daily`, `create_daily_entry`
- [ ] Daily note template support

### Phase 4: Traversal & Polish
- [ ] Tools: `get_linked_notes` with depth traversal
- [ ] Tools: `append_to_note` with heading support
- [ ] Comprehensive test suite
- [ ] Documentation and README

---

## Testing Strategy

### Unit Tests

```python
# tests/test_utils/test_wikilinks.py
import pytest
from obsidian_brain.utils.wikilinks import extract_wikilinks, inject_wikilink

def test_extract_simple_wikilinks():
    content = "See [[Note A]] and [[Note B]]"
    assert extract_wikilinks(content) == ["Note A", "Note B"]

def test_extract_wikilinks_with_aliases():
    content = "See [[Note A|alias]] for more"
    assert extract_wikilinks(content) == ["Note A"]

def test_inject_wikilink_creates_section():
    content = "# Title\n\nSome content"
    result = inject_wikilink(content, "Target Note")
    assert "## See Also" in result
    assert "[[Target Note]]" in result
```

### Integration Tests

```python
# tests/test_client.py
import pytest
from pytest_httpx import HTTPXMock
from obsidian_brain.client import ObsidianClient

@pytest.fixture
async def client():
    async with ObsidianClient(api_key="test") as c:
        yield c

@pytest.mark.asyncio
async def test_list_directory(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://127.0.0.1:27124/vault/",
        json={"files": ["Note.md", "Folder/"]}
    )
    result = await client.list_directory("/")
    assert "Note.md" in [f["name"] for f in result]
```

---

## Security Considerations

1. **API Key Protection**: Never log or expose the API key
2. **Path Validation**: Prevent path traversal attacks (e.g., `../../../etc/passwd`)
3. **SSL Verification**: Self-signed cert handling with explicit opt-out
4. **Docker Isolation**: Run with minimal privileges
5. **Input Validation**: Sanitize all user inputs before API calls

---

## Future Enhancements (Post-MVP)

- [ ] `vault://tags` resource for tag taxonomy
- [ ] `vault://graph` resource for link visualization data
- [ ] Orphan note detection and reporting
- [ ] Template-based note creation with variables
- [ ] Bulk operations (batch tag/link updates)
- [ ] Periodic notes beyond daily (weekly, monthly)
- [ ] Command execution proxy
- [ ] WebSocket support for real-time updates
- [ ] Plugin capability detection (Dataview, Templater)
