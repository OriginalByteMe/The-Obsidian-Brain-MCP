"""
Tests for VaultCache with mocked VaultClient.

Verifies cache refresh uses bulk get_all_files (not recursive directory walk),
semaphore-bounded concurrency for note reads, backlink index construction,
tag aggregation, and empty vault handling.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from obsidian_brain.cache import CacheNotInitializedError, VaultCache


def _make_mock_client(
    files: list[str] | None = None,
    notes: dict[str, dict[str, Any]] | None = None,
) -> AsyncMock:
    """Create a mock VaultClient with canned responses."""
    client = AsyncMock()

    if files is None:
        files = []
    if notes is None:
        notes = {}

    client.get_all_files = AsyncMock(return_value=files)

    async def _get_note(path: str, include_metadata: bool = True) -> dict[str, Any]:
        if path in notes:
            return notes[path]
        return {"content": "", "tags": [], "frontmatter": {}, "modified": None}

    client.get_note = AsyncMock(side_effect=_get_note)

    # list_directory is kept for _get_directory_tree but should NOT be called
    # during normal refresh (we use get_all_files instead)
    client.list_directory = AsyncMock(return_value=[])

    return client


# --- Basic refresh ---


@pytest.mark.asyncio
async def test_refresh_populates_structure():
    """refresh() should populate cache structure with notes and stats."""
    files = ["notes/hello.md", "notes/world.md", "README.md"]
    notes = {
        "notes/hello.md": {
            "content": "# Hello\n\nHello content with [[world]]",
            "tags": ["greeting"],
            "frontmatter": {"status": "draft"},
            "modified": "2026-01-01",
        },
        "notes/world.md": {
            "content": "# World\n\nWorld content",
            "tags": ["place"],
            "frontmatter": {},
            "modified": "2026-01-02",
        },
        "README.md": {
            "content": "# README\n\nProject readme",
            "tags": [],
            "frontmatter": {},
            "modified": None,
        },
    }

    client = _make_mock_client(files, notes)
    cache = VaultCache()

    structure = await cache.refresh(client)

    assert structure.stats.total_notes == 3
    assert cache.is_initialized
    paths = [n.path for n in structure.notes]
    assert "notes/hello.md" in paths
    assert "notes/world.md" in paths


# --- Bulk listing (get_all_files) ---


@pytest.mark.asyncio
async def test_refresh_uses_get_all_files_not_list_directory():
    """refresh() should call get_all_files for bulk listing, not list_directory."""
    client = _make_mock_client(files=["note.md"], notes={})
    cache = VaultCache()

    await cache.refresh(client)

    client.get_all_files.assert_called_once_with("/")
    client.list_directory.assert_not_called()


# --- Semaphore-bounded concurrency ---


@pytest.mark.asyncio
async def test_concurrent_note_reads():
    """All notes should be read even with 20+ files (semaphore allows bounded concurrency)."""
    num_notes = 25
    files = [f"note_{i}.md" for i in range(num_notes)]
    notes = {
        f"note_{i}.md": {
            "content": f"# Note {i}\n\nContent {i}",
            "tags": [f"tag{i % 5}"],
            "frontmatter": {},
            "modified": None,
        }
        for i in range(num_notes)
    }

    # Track concurrency to verify semaphore is used
    max_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    original_get_note = _make_mock_client(files, notes).get_note.side_effect

    async def tracking_get_note(path: str, include_metadata: bool = True):
        nonlocal max_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            if current_concurrent > max_concurrent:
                max_concurrent = current_concurrent
        try:
            if path in notes:
                return notes[path]
            return {"content": "", "tags": [], "frontmatter": {}, "modified": None}
        finally:
            async with lock:
                current_concurrent -= 1

    client = _make_mock_client(files, notes)
    client.get_note = AsyncMock(side_effect=tracking_get_note)

    cache = VaultCache()
    structure = await cache.refresh(client)

    assert structure.stats.total_notes == num_notes
    assert client.get_note.call_count == num_notes
    # Semaphore limits to 10, so max_concurrent should be <= 10
    assert max_concurrent <= 10


# --- Backlink index ---


@pytest.mark.asyncio
async def test_backlink_index_built_correctly():
    """Backlink index should map target -> list of sources that link to it."""
    files = ["a.md", "b.md", "c.md"]
    notes = {
        "a.md": {
            "content": "# A\n\nLinks to [[b]] and [[c]]",
            "tags": [],
            "frontmatter": {},
            "modified": None,
        },
        "b.md": {
            "content": "# B\n\nLinks to [[c]]",
            "tags": [],
            "frontmatter": {},
            "modified": None,
        },
        "c.md": {
            "content": "# C\n\nNo outgoing links",
            "tags": [],
            "frontmatter": {},
            "modified": None,
        },
    }

    client = _make_mock_client(files, notes)
    cache = VaultCache()
    await cache.refresh(client)

    # c.md should have backlinks from a.md and b.md
    backlinks_c = cache.get_backlinks("c.md")
    assert sorted(backlinks_c) == ["a.md", "b.md"]

    # b.md should have backlink from a.md
    backlinks_b = cache.get_backlinks("b.md")
    assert backlinks_b == ["a.md"]

    # a.md has no backlinks
    backlinks_a = cache.get_backlinks("a.md")
    assert backlinks_a == []


# --- Tags ---


@pytest.mark.asyncio
async def test_get_all_tags_returns_counts():
    """get_all_tags should return tag -> count mapping."""
    files = ["a.md", "b.md", "c.md"]
    notes = {
        "a.md": {
            "content": "# A",
            "tags": ["python", "testing"],
            "frontmatter": {},
            "modified": None,
        },
        "b.md": {
            "content": "# B",
            "tags": ["python", "web"],
            "frontmatter": {},
            "modified": None,
        },
        "c.md": {
            "content": "# C",
            "tags": ["testing"],
            "frontmatter": {},
            "modified": None,
        },
    }

    client = _make_mock_client(files, notes)
    cache = VaultCache()
    await cache.refresh(client)

    tags = cache.get_all_tags()
    assert tags == {"python": 2, "testing": 2, "web": 1}


# --- Empty vault ---


@pytest.mark.asyncio
async def test_empty_vault():
    """Cache should handle an empty vault gracefully."""
    client = _make_mock_client(files=[], notes={})
    cache = VaultCache()

    structure = await cache.refresh(client)

    assert structure.stats.total_notes == 0
    assert structure.stats.total_folders == 0
    assert structure.stats.total_tags == 0
    assert structure.stats.total_links == 0
    assert structure.stats.orphan_notes == 0
    assert structure.notes == []
    assert structure.folders == []


# --- Cache not initialized ---


def test_get_structure_before_refresh_raises():
    """Accessing cache before refresh should raise CacheNotInitializedError."""
    cache = VaultCache()
    with pytest.raises(CacheNotInitializedError):
        cache.get_structure()


def test_get_backlinks_before_refresh_raises():
    cache = VaultCache()
    with pytest.raises(CacheNotInitializedError):
        cache.get_backlinks("any.md")


def test_get_all_tags_before_refresh_raises():
    cache = VaultCache()
    with pytest.raises(CacheNotInitializedError):
        cache.get_all_tags()


# --- Folder hierarchy ---


@pytest.mark.asyncio
async def test_folder_hierarchy_built_from_paths():
    """Folders should be derived from file paths."""
    files = [
        "projects/active/todo.md",
        "projects/archive/old.md",
        "notes/idea.md",
        "root.md",
    ]
    notes = {
        fp: {"content": f"# {fp}", "tags": [], "frontmatter": {}, "modified": None}
        for fp in files
    }

    client = _make_mock_client(files, notes)
    cache = VaultCache()
    structure = await cache.refresh(client)

    assert structure.stats.total_folders > 0
    folder_paths = [f.path for f in structure.folders]
    assert "projects/" in folder_paths
    assert "notes/" in folder_paths


# --- Note read failure ---


@pytest.mark.asyncio
async def test_note_read_failure_skipped():
    """Notes that fail to read should be skipped, not crash the refresh."""
    files = ["good.md", "bad.md"]
    notes = {
        "good.md": {
            "content": "# Good",
            "tags": [],
            "frontmatter": {},
            "modified": None,
        },
    }

    async def failing_get_note(path: str, include_metadata: bool = True):
        if path == "bad.md":
            raise RuntimeError("Simulated read failure")
        return notes.get(path, {"content": "", "tags": [], "frontmatter": {}, "modified": None})

    client = _make_mock_client(files, notes)
    client.get_note = AsyncMock(side_effect=failing_get_note)

    cache = VaultCache()
    structure = await cache.refresh(client)

    assert structure.stats.total_notes == 1
    assert structure.notes[0].path == "good.md"


# --- Invalidate path ---


@pytest.mark.asyncio
async def test_invalidate_path():
    """invalidate_path should remove note and its backlink references."""
    files = ["a.md", "b.md"]
    notes = {
        "a.md": {
            "content": "# A\n\nLinks to [[b]]",
            "tags": ["test"],
            "frontmatter": {},
            "modified": None,
        },
        "b.md": {
            "content": "# B",
            "tags": [],
            "frontmatter": {},
            "modified": None,
        },
    }

    client = _make_mock_client(files, notes)
    cache = VaultCache()
    await cache.refresh(client)

    # b.md should have backlink from a.md
    assert cache.get_backlinks("b.md") == ["a.md"]

    # Invalidate a.md
    cache.invalidate_path("a.md")

    # a.md should no longer appear in notes
    assert cache.get_note_metadata("a.md") is None
    # a.md should be removed from b.md's backlinks
    assert cache.get_backlinks("b.md") == []
