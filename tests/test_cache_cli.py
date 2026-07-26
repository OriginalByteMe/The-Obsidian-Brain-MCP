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
from obsidian_brain.exceptions import NoteNotFoundError
from obsidian_brain.parsers import parse_note_read


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

    async def _get_note(path: str) -> dict[str, Any]:
        if path in notes:
            return notes[path]
        return {"content": "", "tags": [], "frontmatter": {}, "modified": None}

    client.get_note = AsyncMock(side_effect=_get_note)

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


@pytest.mark.asyncio
async def test_refresh_indexes_all_files_but_fetches_only_markdown_metadata():
    """The file index is complete while VaultStructure remains note-oriented."""
    files = ["note.md", "assets/cover.png", "board.canvas", "config.yml"]
    client = _make_mock_client(files=files, notes={"note.md": {"content": "# Note"}})
    cache = VaultCache()

    structure = await cache.refresh(client)

    assert cache.get_file_paths() == files
    assert [note.path for note in structure.notes] == ["note.md"]
    client.get_note.assert_awaited_once_with("note.md")


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

    async def tracking_get_note(path: str):
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
        fp: {"content": f"# {fp}", "tags": [], "frontmatter": {}, "modified": None} for fp in files
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

    async def failing_get_note(path: str):
        if path == "bad.md":
            raise RuntimeError("Simulated read failure")
        return notes.get(path, {"content": "", "tags": [], "frontmatter": {}, "modified": None})

    client = _make_mock_client(files, notes)
    client.get_note = AsyncMock(side_effect=failing_get_note)

    cache = VaultCache()
    structure = await cache.refresh(client)

    assert structure.stats.total_notes == 1
    assert structure.notes[0].path == "good.md"


@pytest.mark.asyncio
async def test_refresh_keeps_note_with_malformed_frontmatter():
    raw = "---\ntags: [broken\n---\n# Readable\n"

    async def read_note(path: str) -> dict[str, Any]:
        return parse_note_read(raw, path)

    client = _make_mock_client(["broken.md"])
    client.get_note = AsyncMock(side_effect=read_note)

    structure = await VaultCache().refresh(client)

    assert [note.path for note in structure.notes] == ["broken.md"]
    assert structure.notes[0].tags == []
    assert structure.notes[0].frontmatter == {}


# --- Incremental cache updates ---


def test_invalidate_path_requires_explicit_existence():
    cache = VaultCache()

    with pytest.raises(TypeError):
        cache.invalidate_path("note.md")


@pytest.mark.asyncio
async def test_invalidate_path_updates_membership_and_removes_note_everywhere():
    files = ["a.md", "b.md"]
    notes = {
        "a.md": {
            "content": "# A\n\nLinks to [[b]]",
            "tags": ["old"],
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
    cache = VaultCache()
    await cache.refresh(_make_mock_client(files, notes))
    original_metadata = cache.get_note_metadata("a.md")
    await cache.invalidate_path("a.md", exists=True)
    assert cache.get_note_metadata("a.md") is original_metadata

    await cache.invalidate_path("created.md", exists=True)
    assert cache.get_file_paths() == ["a.md", "b.md", "created.md"]

    await cache.invalidate_path("a.md", exists=False)

    assert cache.get_file_paths() == ["b.md", "created.md"]
    assert cache.get_note_metadata("a.md") is None
    assert cache.get_all_tags() == {}
    assert cache.get_backlinks("b.md") == []
    assert cache.get_note_metadata("b.md").incoming_links == []
    assert cache.get_structure().stats.total_notes == 1
    assert cache.get_structure().stats.total_links == 0


@pytest.mark.asyncio
async def test_invalidate_path_serializes_with_refresh():
    files = ["deleted.md", "kept.md"]
    notes = {
        "deleted.md": {"content": "# Deleted"},
        "kept.md": {"content": "# Kept"},
    }
    cache = VaultCache()
    await cache.refresh(_make_mock_client(files, notes))

    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    async def delayed_listing(path: str) -> list[str]:
        refresh_started.set()
        await release_refresh.wait()
        return files

    client = _make_mock_client(files, notes)
    client.get_all_files = AsyncMock(side_effect=delayed_listing)
    refresh_task = asyncio.create_task(cache.refresh(client))
    await refresh_started.wait()

    delete_task = asyncio.create_task(cache.invalidate_path("deleted.md", exists=False))
    add_task = asyncio.create_task(cache.invalidate_path(".obsidian/layout.json", exists=True))
    await asyncio.sleep(0)

    assert not delete_task.done()
    assert not add_task.done()

    release_refresh.set()
    await asyncio.gather(refresh_task, delete_task, add_task)

    assert cache.get_file_paths() == ["kept.md", ".obsidian/layout.json"]
    assert cache.get_note_metadata("deleted.md") is None


@pytest.mark.asyncio
async def test_sync_note_replaces_metadata_tags_and_link_indexes():
    files = ["a.md", "b.md", "c.md"]
    notes = {
        "a.md": {
            "content": "# Old A\n\nLinks to [[b]]",
            "tags": ["old"],
            "frontmatter": {"status": "old"},
            "modified": None,
        },
        "b.md": {"content": "# B", "tags": [], "frontmatter": {}, "modified": None},
        "c.md": {"content": "# C", "tags": [], "frontmatter": {}, "modified": None},
    }
    client = _make_mock_client(files, notes)
    cache = VaultCache()
    await cache.refresh(client)

    notes["a.md"] = {
        "content": "# New A\n\nLinks to [[c]]",
        "tags": ["new"],
        "frontmatter": {"status": "new"},
        "modified": None,
    }
    await cache.sync_note(client, "a.md")

    metadata = cache.get_note_metadata("a.md")
    assert metadata.title == "New A"
    assert metadata.tags == ["new"]
    assert metadata.outgoing_links == ["c"]
    assert metadata.frontmatter == {"status": "new"}
    assert cache.get_all_tags() == {"new": 1}
    assert cache.get_backlinks("b.md") == []
    assert cache.get_note_metadata("b.md").incoming_links == []
    assert cache.get_backlinks("c.md") == ["a.md"]
    assert cache.get_note_metadata("c.md").incoming_links == ["a.md"]
    assert cache.get_structure().stats.total_links == 1
    client.get_note.assert_awaited_with("a.md")


@pytest.mark.asyncio
async def test_sync_note_inserts_new_note_and_file_membership():
    notes = {
        "target.md": {
            "content": "# Target",
            "tags": [],
            "frontmatter": {},
            "modified": None,
        }
    }
    client = _make_mock_client(["target.md"], notes)
    cache = VaultCache()
    await cache.refresh(client)

    notes["folder/created.md"] = {
        "content": "# Created\n\n[[target]]",
        "tags": ["new"],
        "frontmatter": {},
        "modified": None,
    }
    await cache.sync_note(client, "folder/created.md")

    assert cache.get_file_paths() == ["target.md", "folder/created.md"]
    assert cache.get_note_metadata("folder/created.md").title == "Created"
    assert cache.get_backlinks("target.md") == ["folder/created.md"]
    assert cache.get_note_metadata("target.md").incoming_links == ["folder/created.md"]
    assert cache.get_structure().stats.total_notes == 2
    assert [folder.path for folder in cache.get_structure().folders] == ["folder/"]


@pytest.mark.asyncio
async def test_sync_note_only_tracks_non_markdown_file_membership():
    client = _make_mock_client(["note.md"], {"note.md": {"content": "# Note"}})
    cache = VaultCache()
    await cache.refresh(client)
    client.get_note.reset_mock()

    await cache.sync_note(client, ".obsidian-brain/config.yml")

    assert cache.get_file_paths() == ["note.md", ".obsidian-brain/config.yml"]
    assert cache.get_note_metadata(".obsidian-brain/config.yml") is None
    assert cache.get_structure().stats.total_notes == 1
    client.get_note.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_note_is_a_noop_before_cache_initialization():
    client = AsyncMock()
    cache = VaultCache()

    await cache.sync_note(client, "note.md")

    client.get_note.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_note_keeps_membership_when_the_write_is_not_readable_yet():
    """A post-write read miss keeps membership but never serves stale metadata."""
    notes = {
        "a.md": {
            "content": "# A\n\n[[b]]",
            "tags": ["old"],
            "frontmatter": {},
            "modified": None,
        },
        "b.md": {"content": "# B", "tags": [], "frontmatter": {}, "modified": None},
    }
    client = _make_mock_client(["a.md", "b.md"], notes)
    cache = VaultCache()
    await cache.refresh(client)
    client.get_note = AsyncMock(side_effect=NoteNotFoundError("a.md"))

    await cache.sync_note(client, "a.md")

    assert cache.get_file_paths() == ["a.md", "b.md"]
    assert cache.get_note_metadata("a.md") is None
    assert cache.get_all_tags() == {}
    assert cache.get_backlinks("b.md") == []
    assert cache.get_structure().stats.total_notes == 1


@pytest.mark.asyncio
async def test_sync_note_propagates_operational_read_failures():
    client = _make_mock_client(["a.md"], {"a.md": {"content": "# A"}})
    cache = VaultCache()
    await cache.refresh(client)
    client.get_note = AsyncMock(side_effect=RuntimeError("read failed"))

    with pytest.raises(RuntimeError, match="read failed"):
        await cache.sync_note(client, "a.md")

    assert cache.get_note_metadata("a.md") is not None
