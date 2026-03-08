# Coding Conventions

**Analysis Date:** 2026-03-08

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules
- Tool modules named by domain: `vault.py`, `search.py`, `links.py`, `tags.py`, `daily.py`, `memory.py`, `knowledge.py`, `onboarding.py`
- Utility modules named by function: `frontmatter.py`, `wikilinks.py`
- Package `__init__.py` files contain only a docstring (and version in root package)

**Functions:**
- Use `snake_case` for all functions
- Tool registration functions follow `register_{domain}_tools(server)` pattern
- Private/internal methods prefixed with underscore: `_build_structure()`, `_handle_response()`, `_resolve_link()`
- Async functions use `async def` consistently for all I/O operations

**Variables:**
- Use `snake_case` for all variables and parameters
- Constants use `UPPER_SNAKE_CASE`: `KNOWLEDGE_BASE_PATH`, `CONFIG_PATH`, `MEMORIES_PATH`, `WIKILINK_PATTERN`
- Type hints use Python 3.12 union syntax: `str | None` (not `Optional[str]`)

**Types/Classes:**
- Use `PascalCase` for all classes
- Pydantic models are nouns: `NoteMetadata`, `VaultStructure`, `LinkGraph`, `SearchMatch`
- Exception classes end with `Error`: `ObsidianAPIError`, `NoteNotFoundError`, `CacheNotInitializedError`, `InvalidBacklinkError`
- Manager classes end with `Manager`: `KnowledgeBaseManager`, `MemoryManager`, `OnboardingManager`

## Code Style

**Formatting:**
- Ruff formatter with `line-length = 100`
- Target version: Python 3.12
- Configuration in `pyproject.toml` under `[tool.ruff]`

**Linting:**
- Ruff linter with rule sets: `E` (pycodestyle), `F` (pyflakes), `I` (isort), `UP` (pyupgrade), `B` (bugbear), `SIM` (simplify)
- `E501` (line too long) is ignored (handled by formatter)
- Configuration in `pyproject.toml` under `[tool.ruff.lint]`

**Type Checking:**
- mypy in strict mode
- Configuration in `pyproject.toml` under `[tool.mypy]`
- Target: Python 3.12

## Import Organization

**Order:**
1. Standard library imports (`os`, `re`, `json`, `asyncio`, `datetime`)
2. Third-party imports (`httpx`, `pydantic`, `yaml`, `frontmatter`)
3. Local/relative imports (`from .client import ...`, `from ..cache import ...`)

**Path Style:**
- Use relative imports within the package: `from .models import NoteMetadata`
- Use `from ..` for cross-subpackage imports: `from ..client import ObsidianClient`
- `TYPE_CHECKING` guard for imports only needed for type hints:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_use.server import MCPServer
```

**Import Grouping:**
- Each group separated by a blank line
- Ruff `I` rule enforces isort-compatible ordering

## Error Handling

**Custom Exception Hierarchy:**
- Base: `ObsidianAPIError(Exception)` with `status_code` and `message` attributes - `src/obsidian_brain/client.py`
- Specific: `NoteNotFoundError(ObsidianAPIError)` for 404 responses - `src/obsidian_brain/client.py`
- Domain: `CacheNotInitializedError(Exception)` - `src/obsidian_brain/cache.py`
- Domain: `InvalidBacklinkError(Exception)` - `src/obsidian_brain/tools/vault.py`, `src/obsidian_brain/tools/links.py`

**Tool Error Pattern (prescriptive):**
Tools NEVER raise exceptions to the MCP client. Instead, return JSON error responses:
```python
async def some_tool(path: str) -> str:
    async with ObsidianClient() as client:
        try:
            # ... operation
            return json.dumps({
                "success": True,
                "path": path,
                "message": f"Completed: {path}",
            })
        except NoteNotFoundError:
            return json.dumps({
                "error": True,
                "type": "NoteNotFoundError",
                "message": f"Note not found: {path}",
            })
        except ObsidianAPIError as e:
            return json.dumps({
                "error": True,
                "type": "ObsidianAPIError",
                "message": str(e),
            })
```

**Error Response Structure:**
- Always include `"error": True`
- Always include `"type"` with the exception class name
- Always include `"message"` with a human-readable description
- Optionally include `"suggestion"` with remediation advice
- Optionally include `"path"` for context

**Success Response Structure:**
- Always include `"success": True`
- Always include `"message"` with a human-readable confirmation
- Include relevant data fields

**Input Validation Pattern:**
Validate inputs before performing operations, return early with error JSON:
```python
if not query or not query.strip():
    return json.dumps({
        "error": True,
        "type": "ValidationError",
        "message": "Search query cannot be empty",
    })
```

**Silent Error Handling:**
In cache building (`src/obsidian_brain/cache.py`), exceptions during note metadata fetching are silently caught with `continue` to skip unreadable notes:
```python
try:
    note_data = await client.get_note(file_path, include_metadata=True)
    # ... process
except Exception:
    # Skip notes that can't be read
    continue
```

## Logging

**Framework:** None - no logging framework is used

**Patterns:**
- No logging statements exist in the codebase
- Errors are communicated via return values (JSON) or exceptions
- Silent failures in cache building (bare `except Exception: continue`)

## Comments

**Module Docstrings (mandatory):**
Every `.py` file starts with a module-level docstring describing purpose:
```python
"""
Async HTTP client for Obsidian Local REST API.

Wraps the Obsidian Local REST API endpoints with typed methods
and proper error handling.
"""
```

**Class Docstrings:**
Every class has a docstring explaining purpose. Manager classes include usage examples:
```python
class ObsidianClient:
    """
    Async wrapper for Obsidian Local REST API.

    Handles authentication, SSL verification, and response parsing.
    Uses context manager for proper resource management.

    Example:
        async with ObsidianClient() as client:
            notes = await client.list_directory("/")
    """
```

**Function Docstrings (Google style):**
All public functions use Google-style docstrings with `Args:`, `Returns:`, and optionally `Raises:` and `Example:` sections:
```python
def extract_wikilinks(content: str) -> list[str]:
    """
    Extract all [[wikilink]] targets from content.

    Args:
        content: Markdown content to parse

    Returns:
        List of link targets (note names/paths)

    Example:
        >>> extract_wikilinks("See [[Note A]] and [[Folder/Note B|alias]]")
        ['Note A', 'Folder/Note B']
    """
```

**Section Separators:**
Use comment dividers in the `ObsidianClient` class to group related methods:
```python
# -------------------------------------------------------------------------
# Directory Operations
# -------------------------------------------------------------------------
```

**Inline Comments:**
- Used sparingly and only when logic is non-obvious
- Explain "why" not "what"

## Function Design

**Size:** Functions are generally 10-40 lines. Largest functions are in `src/obsidian_brain/knowledge.py` for content generation.

**Parameters:**
- Use type hints on all parameters
- Use `| None = None` for optional parameters (not `Optional`)
- Use default values for optional params: `context_length: int = 100`
- List parameters default to `None` and are normalized inside: `tags = tags or []`

**Return Values:**
- Tool functions always return `str` (JSON-serialized)
- Client methods return typed values: `dict[str, Any]`, `list[dict[str, Any]]`, `bool`
- Utility functions return specific types: `list[str]`, `tuple[dict, str]`, `str`

## Module Design

**Exports:**
- No `__all__` declarations used anywhere
- Modules export all public names implicitly

**Barrel Files:**
- Package `__init__.py` files contain only docstrings, no re-exports
- Exception: root `__init__.py` exports `__version__`

**Singleton Pattern:**
Manager classes use module-level singleton instances:
```python
# Global singleton instance
vault_cache = VaultCache()
knowledge_manager = KnowledgeBaseManager()
memory_manager = MemoryManager()
onboarding_manager = OnboardingManager()
```

**Tool Registration Pattern:**
Each tool module exports a single `register_{domain}_tools(server)` function that defines tool functions as nested closures decorated with `@server.tool()`:
```python
def register_vault_tools(server: "MCPServer") -> None:
    """Register all vault-related tools with the MCP server."""

    @server.tool()
    async def list_vault_files(path: str = "/") -> str:
        """Tool docstring used by MCP."""
        async with ObsidianClient() as client:
            # ... implementation
```

**Client Usage Pattern:**
Always use `ObsidianClient` as an async context manager. Create a new client per tool invocation:
```python
async with ObsidianClient() as client:
    result = await client.some_method()
```

**Data Model Pattern:**
Use Pydantic `BaseModel` for data structures with `Field(default_factory=...)` for mutable defaults:
```python
class NoteMetadata(BaseModel):
    path: str
    title: str
    tags: list[str] = Field(default_factory=list)
    frontmatter: dict = Field(default_factory=dict)
    modified: datetime | None = None
```

Use `@dataclass` for simple internal data holders (e.g., `Memory` in `src/obsidian_brain/memory.py`, `VaultAnalysis` in `src/obsidian_brain/onboarding.py`).

---

*Convention analysis: 2026-03-08*
