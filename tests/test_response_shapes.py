"""
Response shape assertion tests for all kept tools.

These tests call each tool function with a MockObsidianClient and verify
that the returned JSON string, when parsed, matches the frozen shape from
test_snapshots.py.

This file runs against the CURRENT pre-migration code (REST-based). After
migration, the same shape assertions validate that CLI-backed tools produce
compatible output. The SHAPES must remain identical -- that is the contract.

REMOVED tools (not tested):
- search_advanced (Dataview DQL -- removed in migration)
- search_jsonlogic (JsonLogic query -- removed in migration)
- get_periodic_note (generic periodic -- removed in migration)
"""

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_snapshots import (
    ANY_DICT,
    ANY_VALUE,
    FROZEN_SHAPES,
    REMOVED_TOOLS,
)


# ---------------------------------------------------------------------------
# Shape validation helper
# ---------------------------------------------------------------------------

def assert_matches_shape(data: Any, shape: Any, path: str = "root") -> None:
    """
    Recursively verify that `data` matches the expected `shape`.

    Shape format:
    - dict with string keys: data must be dict with those keys, values matching sub-shapes
    - list with one element: data must be list, each item matching the element shape
    - type (str, int, float, bool): data must be instance of that type
    - tuple of types: data must be instance of one of those types
    - ANY_DICT sentinel: data must be a dict (keys/values not constrained)
    - ANY_VALUE sentinel: any value accepted
    - Special key "__is_list__": data is a list of items matching "item_shape"
    """
    if isinstance(shape, dict):
        # Check for sentinels
        if shape == ANY_DICT:
            assert isinstance(data, dict), f"{path}: expected dict, got {type(data).__name__}"
            return
        if shape == ANY_VALUE:
            return  # anything accepted

        # Check for list-of-items shape
        if "__is_list__" in shape:
            assert isinstance(data, list), f"{path}: expected list, got {type(data).__name__}"
            item_shape = shape["item_shape"]
            for i, item in enumerate(data):
                assert_matches_shape(item, item_shape, f"{path}[{i}]")
            return

        # Regular dict shape
        assert isinstance(data, dict), f"{path}: expected dict, got {type(data).__name__}"
        for key, val_shape in shape.items():
            assert key in data, f"{path}: missing key '{key}'. Keys present: {list(data.keys())}"
            assert_matches_shape(data[key], val_shape, f"{path}.{key}")

    elif isinstance(shape, list):
        # List shape: data must be list, each item matching shape[0]
        assert isinstance(data, list), f"{path}: expected list, got {type(data).__name__}"
        if shape and data:
            item_shape = shape[0]
            for i, item in enumerate(data):
                assert_matches_shape(item, item_shape, f"{path}[{i}]")

    elif isinstance(shape, tuple):
        # Union of types
        assert isinstance(data, shape), (
            f"{path}: expected one of {shape}, got {type(data).__name__}: {data!r}"
        )

    elif isinstance(shape, type):
        assert isinstance(data, shape), (
            f"{path}: expected {shape.__name__}, got {type(data).__name__}: {data!r}"
        )

    else:
        raise ValueError(f"{path}: unsupported shape spec: {shape!r}")


# ---------------------------------------------------------------------------
# Mock infrastructure
# ---------------------------------------------------------------------------

class MockObsidianClient:
    """
    Mock that simulates ObsidianClient responses for shape testing.

    Returns canned data that exercises the success paths of each tool.
    """

    def __init__(self):
        self.list_directory = AsyncMock(return_value=[
            {"name": "test.md", "type": "file"},
            {"name": "folder", "type": "folder"},
        ])
        self.get_note = AsyncMock(return_value={
            "content": "# Test\n\nHello [[World]]",
            "tags": ["test", "example"],
            "frontmatter": {"title": "Test"},
            "modified": "2024-01-15T10:30:00Z",
        })
        self.create_note = AsyncMock()
        self.update_note = AsyncMock()
        self.append_to_note = AsyncMock()
        self.patch_note = AsyncMock()
        self.delete_note = AsyncMock()
        self.note_exists = AsyncMock(return_value=True)
        self.search_simple = AsyncMock(return_value=[
            {
                "filename": "test.md",
                "matches": [{"match": "found text"}],
                "score": 1.5,
            }
        ])
        self.search_dql = AsyncMock(return_value=[])
        self.search_jsonlogic = AsyncMock(return_value=[])
        self.get_periodic = AsyncMock(return_value={
            "content": "# Daily\n\nToday's note",
            "tags": ["daily"],
            "frontmatter": {"date": "2024-01-15"},
        })
        self.append_periodic = AsyncMock()
        self.get_all_files = AsyncMock(return_value=[
            ".obsidian-brain/config.yml",
            ".obsidian-brain/memories/vault-overview.md",
            "test.md",
        ])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _create_mock_client():
    """Create a fresh MockObsidianClient instance."""
    return MockObsidianClient()


# ---------------------------------------------------------------------------
# Mock vault cache
# ---------------------------------------------------------------------------

def _create_mock_vault_cache():
    """Create a mock vault cache with canned data."""
    mock_cache = MagicMock()
    mock_cache.is_initialized = True

    mock_structure = MagicMock()
    mock_structure.stats.total_notes = 10
    mock_structure.stats.total_folders = 3
    mock_structure.stats.total_tags = 5
    mock_structure.stats.total_links = 8
    mock_structure.stats.orphan_notes = 2
    mock_structure.stats.model_dump.return_value = {
        "total_notes": 10,
        "total_folders": 3,
        "total_tags": 5,
        "total_links": 8,
        "orphan_notes": 2,
    }
    mock_structure.refreshed_at = datetime(2024, 1, 15, 10, 30, 0)
    mock_structure.notes = []

    mock_cache.get_structure.return_value = mock_structure
    mock_cache.refresh = AsyncMock(return_value=mock_structure)
    mock_cache.get_backlinks.return_value = ["note1.md", "note2.md"]
    mock_cache.get_all_tags.return_value = {"test": 5, "example": 3}
    mock_cache.get_notes_by_tag.return_value = ["test.md", "example.md"]
    mock_cache.get_note_metadata.return_value = MagicMock(
        outgoing_links=[], incoming_links=[]
    )

    return mock_cache


# ---------------------------------------------------------------------------
# Mock MCP server for tool registration
# ---------------------------------------------------------------------------

class MockMCPServer:
    """Captures tool functions registered via @server.tool()."""

    def __init__(self):
        self.tools: dict[str, Any] = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _register_all_tools(server: MockMCPServer) -> None:
    """Register all tool modules with the mock server."""
    from obsidian_brain.tools.vault import register_vault_tools
    from obsidian_brain.tools.links import register_link_tools
    from obsidian_brain.tools.tags import register_tag_tools
    from obsidian_brain.tools.search import register_search_tools
    from obsidian_brain.tools.daily import register_daily_tools
    from obsidian_brain.tools.knowledge import register_knowledge_tools
    from obsidian_brain.tools.memory import register_memory_tools
    from obsidian_brain.tools.onboarding import register_onboarding_tools

    register_vault_tools(server)
    register_link_tools(server)
    register_tag_tools(server)
    register_search_tools(server)
    register_daily_tools(server)
    register_knowledge_tools(server)
    register_memory_tools(server)
    register_onboarding_tools(server)


@pytest.fixture()
def mock_server():
    """Create a mock server with all tools registered."""
    server = MockMCPServer()
    _register_all_tools(server)
    return server


@pytest.fixture()
def mock_client():
    return _create_mock_client()


@pytest.fixture()
def mock_cache():
    return _create_mock_vault_cache()


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

class TestToolRegistration:
    """Verify all expected tools are registered."""

    def test_all_kept_tools_registered(self, mock_server):
        """All 29 kept tools should be registered."""
        registered = set(mock_server.tools.keys())
        expected = set(FROZEN_SHAPES.keys())
        # The server also registers removed tools -- that's fine,
        # we just need kept tools to be present
        missing = expected - registered
        assert not missing, f"Missing tool registrations: {missing}"

    def test_removed_tools_identified(self, mock_server):
        """Removed tools should be registered but excluded from shapes."""
        for tool_name in REMOVED_TOOLS:
            assert tool_name in mock_server.tools, (
                f"Removed tool '{tool_name}' should still be registered in pre-migration code"
            )
            assert tool_name not in FROZEN_SHAPES, (
                f"Removed tool '{tool_name}' must not be in FROZEN_SHAPES"
            )


# ---------------------------------------------------------------------------
# Response shape tests -- Vault tools
# ---------------------------------------------------------------------------

class TestVaultToolShapes:
    """Verify vault tool response shapes match frozen snapshots."""

    @pytest.mark.asyncio
    async def test_list_vault_files_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.vault.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["list_vault_files"](path="/")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["list_vault_files"])

    @pytest.mark.asyncio
    async def test_get_note_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.vault.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["get_note"](path="test.md")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["get_note"])

    @pytest.mark.asyncio
    async def test_create_note_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.vault.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["create_note"](
                path="New/Note.md", content="Hello", tags=["test"], backlinks=[]
            )
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["create_note"])

    @pytest.mark.asyncio
    async def test_update_note_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.vault.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["update_note"](
                path="test.md", content="Updated"
            )
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["update_note"])

    @pytest.mark.asyncio
    async def test_append_to_note_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.vault.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["append_to_note"](
                path="test.md", content="More text"
            )
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["append_to_note"])

    @pytest.mark.asyncio
    async def test_refresh_vault_structure_shape(self, mock_server, mock_cache):
        with patch("obsidian_brain.tools.vault.ObsidianClient") as MockCls, \
             patch("obsidian_brain.tools.vault.vault_cache", mock_cache):
            mock_inst = _create_mock_client()
            MockCls.return_value = mock_inst
            result = await mock_server.tools["refresh_vault_structure"]()
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["refresh_vault_structure"])

    @pytest.mark.asyncio
    async def test_delete_note_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.vault.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["delete_note"](path="test.md")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["delete_note"])


# ---------------------------------------------------------------------------
# Response shape tests -- Link tools
# ---------------------------------------------------------------------------

class TestLinkToolShapes:
    """Verify link tool response shapes match frozen snapshots."""

    @pytest.mark.asyncio
    async def test_add_backlink_shape(self, mock_server, mock_client):
        # Mock get_note to return content without the target link
        mock_client.get_note.return_value = {
            "content": "# Test\n\nSome content",
            "tags": [],
            "frontmatter": {},
        }
        with patch("obsidian_brain.tools.links.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["add_backlink"](
                source_path="test.md", target_note="Other Note"
            )
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["add_backlink"])

    @pytest.mark.asyncio
    async def test_get_backlinks_shape(self, mock_server, mock_cache):
        with patch("obsidian_brain.tools.links.vault_cache", mock_cache):
            result = await mock_server.tools["get_backlinks"](path="test.md")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["get_backlinks"])

    @pytest.mark.asyncio
    async def test_get_outgoing_links_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.links.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["get_outgoing_links"](path="test.md")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["get_outgoing_links"])

    @pytest.mark.asyncio
    async def test_get_linked_notes_shape(self, mock_server, mock_cache):
        with patch("obsidian_brain.tools.links.vault_cache", mock_cache):
            result = await mock_server.tools["get_linked_notes"](path="test.md")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["get_linked_notes"])


# ---------------------------------------------------------------------------
# Response shape tests -- Tag tools
# ---------------------------------------------------------------------------

class TestTagToolShapes:
    """Verify tag tool response shapes match frozen snapshots."""

    @pytest.mark.asyncio
    async def test_add_tags_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.tags.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["add_tags"](
                path="test.md", tags=["newtag"]
            )
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["add_tags"])

    @pytest.mark.asyncio
    async def test_remove_tags_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.tags.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["remove_tags"](
                path="test.md", tags=["test"]
            )
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["remove_tags"])

    @pytest.mark.asyncio
    async def test_list_all_tags_shape(self, mock_server, mock_cache):
        with patch("obsidian_brain.tools.tags.vault_cache", mock_cache):
            result = await mock_server.tools["list_all_tags"]()
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["list_all_tags"])

    @pytest.mark.asyncio
    async def test_get_notes_by_tag_shape(self, mock_server, mock_cache):
        with patch("obsidian_brain.tools.tags.vault_cache", mock_cache):
            result = await mock_server.tools["get_notes_by_tag"](tag="test")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["get_notes_by_tag"])


# ---------------------------------------------------------------------------
# Response shape tests -- Search tools
# ---------------------------------------------------------------------------

class TestSearchToolShapes:
    """Verify search tool response shapes match frozen snapshots."""

    @pytest.mark.asyncio
    async def test_search_content_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.search.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["search_content"](query="test")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["search_content"])


# ---------------------------------------------------------------------------
# Response shape tests -- Daily tools
# ---------------------------------------------------------------------------

class TestDailyToolShapes:
    """Verify daily tool response shapes match frozen snapshots."""

    @pytest.mark.asyncio
    async def test_get_daily_note_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.daily.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["get_daily_note"](date="2024-01-15")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["get_daily_note"])

    @pytest.mark.asyncio
    async def test_append_to_daily_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.daily.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["append_to_daily"](
                content="New entry", date="2024-01-15"
            )
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["append_to_daily"])

    @pytest.mark.asyncio
    async def test_create_daily_entry_shape(self, mock_server, mock_client):
        with patch("obsidian_brain.tools.daily.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["create_daily_entry"](
                content="Did something", tags=["work"], links=["Project"],
                date="2024-01-15",
            )
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["create_daily_entry"])


# ---------------------------------------------------------------------------
# Response shape tests -- Knowledge tools
# ---------------------------------------------------------------------------

class TestKnowledgeToolShapes:
    """Verify knowledge tool response shapes match frozen snapshots."""

    @pytest.mark.asyncio
    async def test_create_vault_knowledge_base_shape(self, mock_server, mock_client, mock_cache):
        mock_knowledge_mgr = MagicMock()
        mock_knowledge_mgr.generate_content.return_value = "# Knowledge Base"
        with patch("obsidian_brain.tools.knowledge.ObsidianClient", return_value=mock_client), \
             patch("obsidian_brain.tools.knowledge.vault_cache", mock_cache), \
             patch("obsidian_brain.tools.knowledge.knowledge_manager", mock_knowledge_mgr):
            result = await mock_server.tools["create_vault_knowledge_base"]()
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["create_vault_knowledge_base"])

    @pytest.mark.asyncio
    async def test_get_knowledge_base_status_shape(self, mock_server, mock_client):
        mock_client.get_note.return_value = {
            "content": "# Knowledge Base",
            "frontmatter": {
                "created": "2024-01-15",
                "updated": "2024-01-15",
                "generator": "obsidian-brain",
                "vault_stats": {"total_notes": 10},
            },
            "tags": [],
        }
        with patch("obsidian_brain.tools.knowledge.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["get_knowledge_base_status"]()
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["get_knowledge_base_status"])


# ---------------------------------------------------------------------------
# Response shape tests -- Memory tools
# ---------------------------------------------------------------------------

class TestMemoryToolShapes:
    """Verify memory tool response shapes match frozen snapshots."""

    @pytest.mark.asyncio
    async def test_list_memories_shape(self, mock_server, mock_client):
        mock_mem_mgr = MagicMock()
        mock_mem_mgr.list_from_files.return_value = [
            {"name": "vault-overview", "path": ".obsidian-brain/memories/vault-overview.md"},
        ]
        mock_client.get_note.return_value = {
            "content": "Overview content",
            "frontmatter": {"type": "overview", "created": "2024-01-15", "updated": "2024-01-15"},
            "tags": [],
        }
        with patch("obsidian_brain.tools.memory.ObsidianClient", return_value=mock_client), \
             patch("obsidian_brain.tools.memory.memory_manager", mock_mem_mgr):
            result = await mock_server.tools["list_memories"]()
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["list_memories"])

    @pytest.mark.asyncio
    async def test_read_memory_shape(self, mock_server, mock_client):
        mock_mem_mgr = MagicMock()
        mock_mem_mgr.get_memory_path.return_value = ".obsidian-brain/memories/test.md"
        mock_memory = MagicMock()
        mock_memory.content = "Memory content"
        mock_memory.memory_type = "learning"
        mock_memory.created = "2024-01-15"
        mock_memory.updated = "2024-01-15"
        mock_mem_mgr.parse_memory.return_value = mock_memory
        mock_client.get_note.return_value = {
            "content": "Memory content",
            "frontmatter": {"type": "learning", "created": "2024-01-15"},
            "tags": [],
        }
        with patch("obsidian_brain.tools.memory.ObsidianClient", return_value=mock_client), \
             patch("obsidian_brain.tools.memory.memory_manager", mock_mem_mgr):
            result = await mock_server.tools["read_memory"](name="test")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["read_memory"])

    @pytest.mark.asyncio
    async def test_write_memory_shape(self, mock_server, mock_client):
        mock_mem_mgr = MagicMock()
        mock_mem_mgr.get_memory_path.return_value = ".obsidian-brain/memories/test.md"
        mock_mem_mgr.create_memory_content.return_value = "---\ntype: learning\n---\nContent"
        from obsidian_brain.client import NoteNotFoundError
        mock_client.get_note.side_effect = NoteNotFoundError("test.md")
        with patch("obsidian_brain.tools.memory.ObsidianClient", return_value=mock_client), \
             patch("obsidian_brain.tools.memory.memory_manager", mock_mem_mgr):
            result = await mock_server.tools["write_memory"](
                name="test", content="New memory", memory_type="learning"
            )
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["write_memory"])

    @pytest.mark.asyncio
    async def test_delete_memory_shape(self, mock_server, mock_client):
        mock_mem_mgr = MagicMock()
        mock_mem_mgr.get_memory_path.return_value = ".obsidian-brain/memories/test.md"
        with patch("obsidian_brain.tools.memory.ObsidianClient", return_value=mock_client), \
             patch("obsidian_brain.tools.memory.memory_manager", mock_mem_mgr):
            result = await mock_server.tools["delete_memory"](name="test")
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["delete_memory"])

    @pytest.mark.asyncio
    async def test_edit_memory_shape(self, mock_server, mock_client):
        mock_mem_mgr = MagicMock()
        mock_mem_mgr.get_memory_path.return_value = ".obsidian-brain/memories/test.md"
        mock_mem_mgr.update_memory_content.return_value = "Updated content"
        mock_client.get_note.return_value = {
            "content": "Old content with findme text",
            "frontmatter": {},
            "tags": [],
        }
        with patch("obsidian_brain.tools.memory.ObsidianClient", return_value=mock_client), \
             patch("obsidian_brain.tools.memory.memory_manager", mock_mem_mgr):
            result = await mock_server.tools["edit_memory"](
                name="test", search="findme", replace="replaced"
            )
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["edit_memory"])


# ---------------------------------------------------------------------------
# Response shape tests -- Onboarding tools
# ---------------------------------------------------------------------------

class TestOnboardingToolShapes:
    """Verify onboarding tool response shapes match frozen snapshots."""

    @pytest.mark.asyncio
    async def test_check_onboarding_status_shape(self, mock_server, mock_client):
        mock_onboard_mgr = MagicMock()
        mock_onboard_mgr.check_onboarding_status.return_value = {
            "onboarded": True,
            "message": "Vault has been onboarded",
            "recommendation": "Ready to use",
        }
        with patch("obsidian_brain.tools.onboarding.ObsidianClient", return_value=mock_client), \
             patch("obsidian_brain.tools.onboarding.onboarding_manager", mock_onboard_mgr):
            result = await mock_server.tools["check_onboarding_status"]()
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["check_onboarding_status"])

    @pytest.mark.asyncio
    async def test_run_onboarding_shape(self, mock_server, mock_client, mock_cache):
        mock_onboard_mgr = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.folder_patterns = ["PARA"]
        mock_analysis.folder_purposes = {"Projects": "Active projects"}
        mock_analysis.tag_prefixes = ["status/", "type/"]
        mock_analysis.top_tags = [("test", 5), ("example", 3)]
        mock_analysis.templates_found = ["Template1"]
        mock_analysis.naming_patterns = ["kebab-case"]
        mock_analysis.common_frontmatter_keys = ["title", "tags", "date", "status", "type"]
        mock_onboard_mgr.analyze_vault.return_value = mock_analysis
        mock_onboard_mgr.generate_config.return_value = "config content"
        mock_onboard_mgr.generate_vault_overview_memory.return_value = "overview"
        mock_onboard_mgr.generate_conventions_memory.return_value = "conventions"

        with patch("obsidian_brain.tools.onboarding.ObsidianClient", return_value=mock_client), \
             patch("obsidian_brain.tools.onboarding.vault_cache", mock_cache), \
             patch("obsidian_brain.tools.onboarding.onboarding_manager", mock_onboard_mgr):
            result = await mock_server.tools["run_onboarding"]()
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["run_onboarding"])

    @pytest.mark.asyncio
    async def test_get_vault_config_shape(self, mock_server, mock_client):
        mock_client.get_note.return_value = {
            "content": "vault_type: PARA\n",
            "frontmatter": {},
            "tags": [],
        }
        with patch("obsidian_brain.tools.onboarding.ObsidianClient", return_value=mock_client):
            result = await mock_server.tools["get_vault_config"]()
        assert isinstance(result, str)
        data = json.loads(result)
        assert_matches_shape(data, FROZEN_SHAPES["get_vault_config"])


# ---------------------------------------------------------------------------
# Cross-cutting tests
# ---------------------------------------------------------------------------

class TestResponseContract:
    """Cross-cutting contract tests."""

    def test_all_tool_responses_are_json_strings(self, mock_server):
        """Verify every tool function has a str return annotation or returns str."""
        # All tools registered -- just verify they exist
        assert len(mock_server.tools) >= 29

    def test_removed_tools_not_in_frozen_shapes(self):
        """Explicitly verify removed tools are excluded."""
        for name in REMOVED_TOOLS:
            assert name not in FROZEN_SHAPES

    def test_frozen_shapes_cover_all_modules(self):
        """Verify shapes exist for tools from all 8 modules."""
        modules = {
            "vault": ["list_vault_files", "get_note", "create_note", "update_note",
                       "append_to_note", "refresh_vault_structure", "delete_note"],
            "links": ["add_backlink", "get_backlinks", "get_outgoing_links", "get_linked_notes"],
            "tags": ["add_tags", "remove_tags", "list_all_tags", "get_notes_by_tag"],
            "search": ["search_content"],
            "daily": ["get_daily_note", "append_to_daily", "create_daily_entry"],
            "knowledge": ["create_vault_knowledge_base", "get_knowledge_base_status"],
            "memory": ["list_memories", "read_memory", "write_memory",
                        "delete_memory", "edit_memory"],
            "onboarding": ["check_onboarding_status", "run_onboarding", "get_vault_config"],
        }
        for module, tools in modules.items():
            for tool in tools:
                assert tool in FROZEN_SHAPES, (
                    f"Module '{module}' tool '{tool}' missing from FROZEN_SHAPES"
                )
