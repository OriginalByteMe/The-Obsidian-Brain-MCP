# Technical Design: Dynamic Vault Resources & Search Fix

## Overview

This document specifies the technical design for:
1. **FR1**: Fix search validation bug
2. **FR2**: Dynamic note resources (`vault://note/{path}`)
3. **FR3**: Dynamic folder resources (`vault://folder/{path}`)
4. **FR4**: Enhanced search with content retrieval

## Architecture

### Current State

```
src/obsidian_brain/
├── resources/
│   ├── structure.py    # vault://structure, vault://tags, vault://stats
│   └── knowledge.py    # vault://knowledge
├── tools/
│   └── search.py       # search_content (buggy), search_advanced, search_jsonlogic
├── client.py           # ObsidianClient HTTP wrapper
├── cache.py            # VaultCache singleton
└── models.py           # Pydantic models
```

### Target State

```
src/obsidian_brain/
├── resources/
│   ├── structure.py    # (unchanged)
│   ├── knowledge.py    # (unchanged)
│   └── vault_access.py # NEW: vault://note/{path}, vault://folder/{path}
├── tools/
│   └── search.py       # FIXED: search_content
└── ...
```

---

## Component Designs

### 1. Search Bug Fix (FR1)

**File**: `src/obsidian_brain/tools/search.py`

**Problem**: Line 62 extracts `m.get("match")` which returns `{"start": int, "end": int}` instead of the text.

**Solution**: Use `m.get("context")` which contains the actual text snippet.

**Change**:
```python
# Before (line 58-64):
match_texts = []
for m in snippets:
    if isinstance(m, dict):
        match_texts.append(m.get("match", str(m)))  # WRONG
    else:
        match_texts.append(str(m))

# After:
match_texts = []
for m in snippets:
    if isinstance(m, dict):
        # API returns: {"match": {"start": N, "end": N}, "context": "...text..."}
        match_texts.append(m.get("context", str(m)))  # CORRECT
    else:
        match_texts.append(str(m))
```

**Impact**: Minimal - single line change, backwards compatible.

---

### 2. Dynamic Note Resource (FR2)

**File**: `src/obsidian_brain/resources/vault_access.py` (new)

**URI Pattern**: `vault://note/{path:path}`

The `:path` suffix allows slashes in the parameter (e.g., `Projects/MyNote.md`).

**Interface**:
```python
@server.resource(
    uri="vault://note/{path:path}",
    name="vault_note",
    title="Vault Note",
    description="Read a specific note from the vault by path",
    mime_type="text/markdown"
)
async def get_vault_note(path: str) -> str:
    """
    Returns the full content of a note including frontmatter.

    Args:
        path: Note path relative to vault root (e.g., "Projects/MyNote.md")

    Returns:
        Full note content as markdown

    Raises:
        ValueError: If note not found
    """
```

**Response Format** (markdown):
```markdown
---
tags: [project, active]
created: 2024-01-15
---

# My Note Title

Note content here...
```

**Error Handling**:
- Note not found: Return error message in markdown format
- API error: Return error message with details

---

### 3. Dynamic Folder Resource (FR3)

**File**: `src/obsidian_brain/resources/vault_access.py`

**URI Pattern**: `vault://folder/{path:path}`

**Behavior**:
- Recursive listing (includes all subfolders)
- List-only (paths and titles, no content)
- Uses cache when available, falls back to API

**Interface**:
```python
@server.resource(
    uri="vault://folder/{path:path}",
    name="vault_folder",
    title="Vault Folder",
    description="List all notes in a folder recursively",
    mime_type="application/json"
)
async def get_vault_folder(path: str) -> str:
    """
    Returns a recursive listing of all notes in a folder.

    Args:
        path: Folder path relative to vault root (e.g., "Projects")

    Returns:
        JSON array of note metadata (path, title, tags)
    """
```

**Response Format** (JSON):
```json
{
  "folder": "Projects",
  "notes": [
    {
      "path": "Projects/MyProject.md",
      "title": "My Project",
      "tags": ["project", "active"]
    },
    {
      "path": "Projects/Archive/OldProject.md",
      "title": "Old Project",
      "tags": ["project", "archived"]
    }
  ],
  "subfolders": ["Projects/Archive", "Projects/Ideas"],
  "total_notes": 15
}
```

**Cache Strategy**:
1. Check if `vault_cache.is_initialized`
2. If yes: Filter cached notes by path prefix (fast)
3. If no: Make direct API calls (slower but works without refresh)

---

### 4. Enhanced Search (FR4)

**File**: `src/obsidian_brain/tools/search.py`

**Enhancement**: Add optional `include_content` parameter to `search_content`.

**Interface Change**:
```python
@server.tool()
async def search_content(
    query: str,
    context_length: int = 100,
    include_content: bool = False,  # NEW
    max_results: int = 10,          # NEW
) -> str:
    """
    Search for text across all notes in the vault.

    Args:
        query: Search query string
        context_length: Characters of context around matches (default 100)
        include_content: If True, fetch full content of matching notes
        max_results: Maximum number of results to return (default 10)
    """
```

**Response Format** (with `include_content=True`):
```json
{
  "success": true,
  "query": "project",
  "results": [
    {
      "path": "Projects/MyProject.md",
      "matches": ["...context around match..."],
      "score": 0.95,
      "content": "---\ntags: [project]\n---\n\n# My Project\n\nFull note content..."
    }
  ],
  "total_matches": 5
}
```

---

## Data Flow Diagrams

### Note Resource Flow

```
Claude Code: @vault://note/Projects/MyNote.md
     │
     ▼
MCP Client → get_vault_note(path="Projects/MyNote.md")
     │
     ▼
ObsidianClient.get_note(path, include_metadata=True)
     │
     ▼
Obsidian Local REST API: GET /vault/Projects/MyNote.md
     │
     ▼
Response: {content, tags, frontmatter, modified}
     │
     ▼
Format as markdown with frontmatter
     │
     ▼
Return to Claude Code context
```

### Folder Resource Flow

```
Claude Code: @vault://folder/Projects
     │
     ▼
MCP Client → get_vault_folder(path="Projects")
     │
     ├─── Cache initialized?
     │         │
     │    YES  │  NO
     │    ▼    ▼
     │  Filter cached notes    ObsidianClient.get_all_files("Projects")
     │  by path.startswith()        │
     │         │                    ▼
     │         │              Fetch metadata for each .md file
     │         │                    │
     │         ▼                    ▼
     │    Return filtered      Return collected notes
     │         │                    │
     └─────────┴────────────────────┘
                    │
                    ▼
              Format as JSON
                    │
                    ▼
           Return to Claude Code
```

---

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `tools/search.py` | MODIFY | Fix line 62: `context` instead of `match` |
| `tools/search.py` | MODIFY | Add `include_content` and `max_results` params |
| `resources/vault_access.py` | CREATE | New file with note and folder resources |
| `server.py` | MODIFY | Import and register `vault_access` resources |
| `server.py` | MODIFY | Update instructions with new resources |
| `models.py` | MODIFY | Add `FolderListing` model (optional) |

---

## New Model (Optional)

```python
# models.py

class FolderListing(BaseModel):
    """Response for folder resource listing."""

    folder: str
    notes: list[NoteMetadata] = Field(default_factory=list)
    subfolders: list[str] = Field(default_factory=list)
    total_notes: int = 0
```

---

## Security Considerations

1. **Path Traversal**: The `:path` parameter allows any path. The Obsidian API already validates paths are within the vault, so no additional validation needed.

2. **Large Folders**: For very large folders, consider adding a warning in the response when >100 notes are returned.

3. **Rate Limiting**: The Obsidian Local REST API handles its own rate limiting; no additional measures needed.

---

## Testing Strategy

1. **Unit Tests**:
   - `test_search_content_extracts_context()` - Verify context field is used
   - `test_note_resource_returns_content()` - Verify note fetching
   - `test_folder_resource_recursive()` - Verify recursive listing
   - `test_folder_resource_uses_cache()` - Verify cache optimization

2. **Integration Tests**:
   - Test with actual Obsidian vault
   - Verify `@` references work in Claude Code

---

## Implementation Order

1. **Phase 1**: Fix search bug (FR1) - Critical, quick win
2. **Phase 2**: Add note resource (FR2) - High value, simple
3. **Phase 3**: Add folder resource (FR3) - Depends on cache understanding
4. **Phase 4**: Enhanced search (FR4) - Nice to have, builds on FR1

---

## Rollback Plan

All changes are additive except the search fix:
- New resources can be unregistered by removing imports
- Search fix is a single line change that can be reverted
- No database migrations or breaking changes
