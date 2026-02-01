# Implementation Workflow: Dynamic Vault Resources & Search Fix

**Generated**: 2026-01-30
**Source**: `docs/design-dynamic-resources.md`
**Strategy**: Systematic (phased approach with dependency ordering)

---

## Overview

This workflow implements four feature requests:
- **FR1**: Fix search validation bug (critical, quick win)
- **FR2**: Dynamic note resources (`vault://note/{path}`)
- **FR3**: Dynamic folder resources (`vault://folder/{path}`)
- **FR4**: Enhanced search with content retrieval

---

## Phase 1: Search Bug Fix (FR1)

**Priority**: Critical
**Dependencies**: None
**Files Modified**: 1

### Task 1.1: Fix search_content context extraction

**File**: `src/obsidian_brain/tools/search.py`

**Problem**: Line 62 extracts `m.get("match")` which returns `{"start": int, "end": int}` (position data) instead of the actual text.

**Change**:
```python
# Line 62 - Change:
match_texts.append(m.get("match", str(m)))
# To:
match_texts.append(m.get("context", str(m)))
```

**Verification**:
- [ ] Change line 62 in `search.py`
- [ ] Manually verify with a test search (requires Obsidian running)

---

## Phase 2: Dynamic Note Resource (FR2)

**Priority**: High
**Dependencies**: None (can run parallel with Phase 1)
**Files Modified**: 3

### Task 2.1: Create vault_access.py resource module

**File**: `src/obsidian_brain/resources/vault_access.py` (NEW)

**Implementation**:
```python
"""
Dynamic vault access resources for Obsidian Brain MCP.

Provides resources for accessing individual notes and folder listings.
"""

import json
from typing import TYPE_CHECKING

from ..client import ObsidianClient, NoteNotFoundError, ObsidianAPIError

if TYPE_CHECKING:
    from mcp_use.server import MCPServer


def register_vault_access_resources(server: "MCPServer") -> None:
    """Register dynamic vault access resources with the MCP server."""

    @server.resource(
        uri="vault://note/{path:path}",
        mime_type="text/markdown"
    )
    async def get_vault_note(path: str) -> str:
        """
        Read a specific note from the vault by path.

        Returns the full content including frontmatter as markdown.

        Args:
            path: Note path relative to vault root (e.g., "Projects/MyNote.md")

        Returns:
            Full note content as markdown
        """
        async with ObsidianClient() as client:
            try:
                note_data = await client.get_note(path, include_metadata=True)

                # Return full content (already includes frontmatter)
                return note_data.get("content", "")

            except NoteNotFoundError:
                return f"# Error: Note Not Found\n\nThe note `{path}` does not exist in the vault."
            except ObsidianAPIError as e:
                return f"# Error: API Error\n\n{e.message}"
```

**Verification**:
- [ ] Create the file with the note resource
- [ ] Ensure imports are correct

### Task 2.2: Register vault_access resources in server.py

**File**: `src/obsidian_brain/server.py`

**Changes**:
1. Add import at line ~11:
   ```python
   from .resources.vault_access import register_vault_access_resources
   ```

2. Add registration after line 149:
   ```python
   register_vault_access_resources(server)
   ```

**Verification**:
- [ ] Add import statement
- [ ] Add registration call

### Task 2.3: Update server instructions

**File**: `src/obsidian_brain/server.py`

**Change**: Add to `## Available Resources` section (around line 63-68):
```python
- `vault://note/{path}` - Read a specific note by path (e.g., vault://note/Projects/MyNote.md)
```

**Verification**:
- [ ] Update instructions docstring

---

## Phase 3: Dynamic Folder Resource (FR3)

**Priority**: Medium
**Dependencies**: Phase 2 (shared module)
**Files Modified**: 2

### Task 3.1: Add folder resource to vault_access.py

**File**: `src/obsidian_brain/resources/vault_access.py`

**Implementation** (add to existing file):
```python
    @server.resource(
        uri="vault://folder/{path:path}",
        mime_type="application/json"
    )
    async def get_vault_folder(path: str) -> str:
        """
        List all notes in a folder recursively.

        Returns JSON with folder metadata, notes list, and subfolders.
        Uses cache when available for performance.

        Args:
            path: Folder path relative to vault root (e.g., "Projects")

        Returns:
            JSON object with folder listing
        """
        from ..cache import vault_cache, CacheNotInitializedError

        try:
            # Try to use cache first (faster)
            if vault_cache.is_initialized:
                structure = vault_cache.get_structure()

                # Normalize path for comparison
                folder_prefix = path.rstrip("/") + "/" if path else ""
                if folder_prefix == "/":
                    folder_prefix = ""

                # Filter notes by path prefix
                matching_notes = []
                subfolders = set()

                for note in structure.notes:
                    if note.path.startswith(folder_prefix):
                        matching_notes.append({
                            "path": note.path,
                            "title": note.title,
                            "tags": note.tags,
                        })

                        # Extract immediate subfolders
                        remaining_path = note.path[len(folder_prefix):]
                        if "/" in remaining_path:
                            subfolder = folder_prefix + remaining_path.split("/")[0]
                            subfolders.add(subfolder)

                result = {
                    "folder": path,
                    "notes": matching_notes,
                    "subfolders": sorted(list(subfolders)),
                    "total_notes": len(matching_notes),
                }
                return json.dumps(result, indent=2)

        except CacheNotInitializedError:
            pass  # Fall through to API approach

        # Fallback: Use API directly (slower but works without cache)
        async with ObsidianClient() as client:
            try:
                all_files = await client.get_all_files(path)
                md_files = [f for f in all_files if f.endswith(".md")]

                notes = []
                for file_path in md_files:
                    try:
                        note_data = await client.get_note(file_path, include_metadata=True)
                        # Extract title from filename
                        title = file_path.split("/")[-1]
                        if title.endswith(".md"):
                            title = title[:-3]

                        notes.append({
                            "path": file_path,
                            "title": title,
                            "tags": note_data.get("tags", []),
                        })
                    except Exception:
                        continue

                # Extract subfolders from file paths
                subfolders = set()
                folder_prefix = path.rstrip("/") + "/" if path else ""
                for file_path in md_files:
                    remaining = file_path[len(folder_prefix):]
                    if "/" in remaining:
                        subfolder = folder_prefix + remaining.split("/")[0]
                        subfolders.add(subfolder)

                result = {
                    "folder": path,
                    "notes": notes,
                    "subfolders": sorted(list(subfolders)),
                    "total_notes": len(notes),
                }
                return json.dumps(result, indent=2)

            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "message": f"Failed to list folder: {e.message}"
                })
```

**Verification**:
- [ ] Add folder resource function to vault_access.py
- [ ] Ensure cache and API fallback both work

### Task 3.2: Update server instructions for folder resource

**File**: `src/obsidian_brain/server.py`

**Change**: Add to `## Available Resources` section:
```python
- `vault://folder/{path}` - List all notes in a folder recursively (e.g., vault://folder/Projects)
```

**Verification**:
- [ ] Update instructions docstring

---

## Phase 4: Enhanced Search (FR4)

**Priority**: Nice-to-have
**Dependencies**: Phase 1 (search fix)
**Files Modified**: 1

### Task 4.1: Add include_content and max_results parameters

**File**: `src/obsidian_brain/tools/search.py`

**Changes to search_content function**:

1. Update function signature (lines 22-25):
```python
async def search_content(
    query: str,
    context_length: int = 100,
    include_content: bool = False,
    max_results: int = 10,
) -> str:
```

2. Update docstring to document new parameters

3. Add content fetching logic after building matches (around line 70):
```python
# Apply max_results limit
matches = matches[:max_results]

# Optionally fetch full content
if include_content:
    for match in matches:
        try:
            note_data = await client.get_note(match["path"], include_metadata=True)
            match["content"] = note_data.get("content", "")
        except Exception:
            match["content"] = None
```

**Verification**:
- [ ] Update function signature
- [ ] Update docstring
- [ ] Add content fetching logic
- [ ] Test with `include_content=True`

---

## Phase 5: Models (Optional)

**Priority**: Low
**Dependencies**: Phase 3
**Files Modified**: 1

### Task 5.1: Add FolderListing model

**File**: `src/obsidian_brain/models.py`

**Implementation** (add after SearchMatch class):
```python
class FolderListing(BaseModel):
    """Response for folder resource listing."""

    folder: str
    notes: list[NoteMetadata] = Field(default_factory=list)
    subfolders: list[str] = Field(default_factory=list)
    total_notes: int = 0
```

**Note**: This is optional - the inline dict approach in Phase 3 works fine.

**Verification**:
- [ ] Add model if needed for type safety

---

## Phase 6: Testing

**Priority**: Medium
**Dependencies**: All phases complete
**Files Modified**: 1-2 (new test files)

### Task 6.1: Create unit tests

**File**: `tests/test_search.py` (NEW)

**Tests to implement**:
```python
def test_search_content_extracts_context():
    """Verify context field is used instead of match positions."""
    pass

def test_search_content_with_include_content():
    """Verify include_content fetches full note content."""
    pass

def test_search_content_respects_max_results():
    """Verify max_results limits output."""
    pass
```

**File**: `tests/test_resources.py` (NEW)

**Tests to implement**:
```python
def test_note_resource_returns_content():
    """Verify vault://note/{path} returns note content."""
    pass

def test_note_resource_handles_not_found():
    """Verify graceful error for missing notes."""
    pass

def test_folder_resource_recursive():
    """Verify folder resource lists all nested notes."""
    pass

def test_folder_resource_uses_cache():
    """Verify cache is used when initialized."""
    pass
```

**Verification**:
- [ ] Create test files
- [ ] Run tests with pytest

---

## Execution Order Summary

```
Phase 1 (FR1)     Phase 2 (FR2)
    │                 │
    │                 ├─ Task 2.1: Create vault_access.py
    │                 ├─ Task 2.2: Register in server.py
    │                 └─ Task 2.3: Update instructions
    │                 │
    ├─────────────────┘
    │
    ▼
Phase 3 (FR3) ─────────────────────────────────────┐
    │                                              │
    ├─ Task 3.1: Add folder resource               │
    └─ Task 3.2: Update instructions               │
    │                                              │
    ▼                                              │
Phase 4 (FR4) ◄────────────────────────────────────┘
    │
    ├─ Task 4.1: Add include_content parameter
    │
    ▼
Phase 5 (Optional) ───► Phase 6 (Testing)
```

---

## Checkpoints

### Checkpoint 1: After Phase 1
- [ ] Search results show actual text context, not position objects
- [ ] No regressions in existing search functionality

### Checkpoint 2: After Phase 2
- [ ] `vault://note/path/to/note.md` returns note content
- [ ] Error handling for missing notes works

### Checkpoint 3: After Phase 3
- [ ] `vault://folder/Projects` returns JSON listing
- [ ] Cache-based lookup works when cache is initialized
- [ ] API fallback works when cache is not initialized

### Checkpoint 4: After Phase 4
- [ ] `search_content(query, include_content=True)` fetches content
- [ ] `max_results` limits the number of results returned

### Checkpoint 5: After Phase 6
- [ ] All unit tests pass
- [ ] No linting errors

---

## Rollback Plan

All changes are additive except the search fix:
- New resources can be unregistered by removing imports from server.py
- Search fix is a single word change (`match` → `context`) that can be reverted
- No database migrations or breaking changes

---

## Files Changed Summary

| File | Change Type | Phase |
|------|-------------|-------|
| `tools/search.py` | MODIFY | 1, 4 |
| `resources/vault_access.py` | CREATE | 2, 3 |
| `server.py` | MODIFY | 2, 3 |
| `models.py` | MODIFY (optional) | 5 |
| `tests/test_search.py` | CREATE | 6 |
| `tests/test_resources.py` | CREATE | 6 |
