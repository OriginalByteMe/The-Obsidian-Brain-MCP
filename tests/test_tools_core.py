"""
Tests for core tool modules with mocked VaultClient.

Verifies that migrated tools call the correct VaultClient methods
and return expected JSON shapes.
"""

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp.server.fastmcp import FastMCP

from obsidian_brain.exceptions import NoteNotFoundError, ObsidianCLIError
from obsidian_brain.protocol import VaultClient


class MockVaultClient:
    """Mock VaultClient that satisfies the Protocol with canned responses."""

    def __init__(self):
        self.list_directory = AsyncMock(return_value=[
            {"name": "note1.md", "type": "file"},
            {"name": "folder1", "type": "folder"},
        ])
        self.get_all_files = AsyncMock(return_value=["note1.md", "folder1/note2.md"])
        self.get_note = AsyncMock(return_value={
            "content": "# Test Note\n\nSome content with [[link1]].",
            "tags": ["test", "example"],
            "frontmatter": {"title": "Test Note"},
            "modified": "2026-03-08T00:00:00Z",
        })
        self.note_exists = AsyncMock(return_value=True)
        self.create_note = AsyncMock()
        self.update_note = AsyncMock()
        self.append_to_note = AsyncMock()
        self.delete_note = AsyncMock()
        self.search_simple = AsyncMock(return_value=[
            {
                "filename": "note1.md",
                "matches": [{"match": "found text"}],
                "score": 1.0,
            }
        ])
        self.get_daily_note = AsyncMock(return_value={
            "content": "# 2026-03-08\n\nDaily content",
            "tags": ["daily"],
            "frontmatter": {"date": "2026-03-08"},
        })
        self.append_daily = AsyncMock()
        self.get_tags = AsyncMock(return_value={"test": 5, "example": 3})
        self.get_backlinks = AsyncMock(return_value=["note2.md"])
        self.get_links = AsyncMock(return_value=["note3.md"])


def _make_server_and_client():
    """Create a fresh FastMCP server and MockVaultClient for testing."""
    server = FastMCP("test-server")
    client = MockVaultClient()
    return server, client


def _load_tool_result(result: tuple[list[Any], dict[str, str]]) -> Any:
    """Extract the JSON payload returned by FastMCP call_tool."""
    _, metadata = result
    return json.loads(metadata["result"])


class TestVaultTools:
    """Test vault tool module with mocked VaultClient."""

    @pytest.fixture
    def setup(self):
        from obsidian_brain.tools.vault import register_vault_tools

        server, client = _make_server_and_client()
        register_vault_tools(server, client)
        return server, client

    @pytest.mark.anyio
    async def test_get_note_returns_json(self, setup):
        server, client = setup
        # Find the get_note tool function
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "get_note" in tool_names

    @pytest.mark.anyio
    async def test_get_note_calls_client(self, setup):
        server, client = setup
        result = await server.call_tool("get_note", {"path": "test.md"})
        client.get_note.assert_called_once()

    @pytest.mark.anyio
    async def test_get_note_result_shape(self, setup):
        server, client = setup
        result = await server.call_tool("get_note", {"path": "test.md"})
        data = _load_tool_result(result)
        assert "path" in data
        assert "content" in data
        assert "tags" in data

    @pytest.mark.anyio
    async def test_create_note_calls_client(self, setup):
        server, client = setup
        result = await server.call_tool("create_note", {
            "path": "new/note.md",
            "content": "Hello world",
        })
        client.create_note.assert_called_once()
        data = _load_tool_result(result)
        assert data["success"] is True

    @pytest.mark.anyio
    async def test_delete_note_calls_client(self, setup):
        server, client = setup
        result = await server.call_tool("delete_note", {"path": "test.md"})
        client.delete_note.assert_called_once()
        data = _load_tool_result(result)
        assert data["success"] is True

    @pytest.mark.anyio
    async def test_list_vault_files(self, setup):
        server, client = setup
        result = await server.call_tool("list_vault_files", {"path": "/"})
        client.list_directory.assert_called_once()
        data = _load_tool_result(result)
        assert isinstance(data, list)
        assert len(data) == 2


class TestSearchTools:
    """Test search tool module with mocked VaultClient."""

    @pytest.fixture
    def setup(self):
        from obsidian_brain.tools.search import register_search_tools

        server, client = _make_server_and_client()
        register_search_tools(server, client)
        return server, client

    @pytest.mark.anyio
    async def test_search_content_calls_client(self, setup):
        server, client = setup
        result = await server.call_tool("search_content", {"query": "test"})
        client.search_simple.assert_called_once()
        data = _load_tool_result(result)
        assert data["success"] is True
        assert data["total_matches"] == 1

    @pytest.mark.anyio
    async def test_search_content_empty_query(self, setup):
        server, client = setup
        result = await server.call_tool("search_content", {"query": ""})
        data = _load_tool_result(result)
        assert data["error"] is True
        assert data["type"] == "ValidationError"

    @pytest.mark.anyio
    async def test_removed_tools_not_registered(self, setup):
        server, _ = setup
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "search_advanced" not in tool_names
        assert "search_jsonlogic" not in tool_names


class TestDailyTools:
    """Test daily tool module with mocked VaultClient."""

    @pytest.fixture
    def setup(self):
        from obsidian_brain.tools.daily import register_daily_tools

        server, client = _make_server_and_client()
        register_daily_tools(server, client)
        return server, client

    @pytest.mark.anyio
    async def test_get_daily_note_calls_client(self, setup):
        server, client = setup
        result = await server.call_tool("get_daily_note", {"date": "2026-03-08"})
        client.get_daily_note.assert_called_once()
        data = _load_tool_result(result)
        assert data["success"] is True
        assert data["date"] == "2026-03-08"

    @pytest.mark.anyio
    async def test_get_daily_note_invalid_date(self, setup):
        server, client = setup
        result = await server.call_tool("get_daily_note", {"date": "not-a-date"})
        data = _load_tool_result(result)
        assert data["error"] is True
        assert data["type"] == "ValidationError"

    @pytest.mark.anyio
    async def test_removed_periodic_not_registered(self, setup):
        server, _ = setup
        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "get_periodic_note" not in tool_names
        # Daily tools should be present
        assert "get_daily_note" in tool_names
        assert "append_to_daily" in tool_names
        assert "create_daily_entry" in tool_names

    @pytest.mark.anyio
    async def test_append_to_daily_calls_client(self, setup):
        server, client = setup
        result = await server.call_tool("append_to_daily", {
            "content": "Test entry",
            "date": "2026-03-08",
        })
        client.append_daily.assert_called_once()
        data = _load_tool_result(result)
        assert data["success"] is True
