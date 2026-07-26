"""
Tests for core tool modules with mocked VaultClient.

Verifies that migrated tools call the correct VaultClient methods
and return expected JSON shapes.
"""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from obsidian_brain.exceptions import (
    CLINotFoundError,
    CLITimeoutError,
    ObsidianCLIError,
    ObsidianNotRunningError,
)


class MockVaultClient:
    """Mock VaultClient that satisfies the Protocol with canned responses."""

    def __init__(self):
        self.list_directory = AsyncMock(
            return_value=[
                {"name": "note1.md", "type": "file"},
                {"name": "sub/note2.md", "type": "file"},
            ]
        )
        self.get_all_files = AsyncMock(return_value=["note1.md", "folder1/note2.md"])
        self.get_note = AsyncMock(
            return_value={
                "content": "# Test Note\n\nSome content with [[link1]].",
                "tags": ["test", "example"],
                "frontmatter": {"title": "Test Note"},
                "modified": "2026-03-08T00:00:00Z",
            }
        )
        self.note_exists = AsyncMock(return_value=True)
        self.create_note = AsyncMock(side_effect=lambda path, content: path)
        self.update_note = AsyncMock()
        self.append_to_note = AsyncMock()
        self.delete_note = AsyncMock()
        self.search_simple = AsyncMock(
            return_value=[
                {
                    "path": "note1.md",
                    "matches": ["first context", "second context"],
                    "score": 1.0,
                }
            ]
        )
        self.get_daily_path = AsyncMock(return_value="Daily/2026-03-08.md")
        self.get_daily_note = AsyncMock(
            return_value={
                "content": "# 2026-03-08\n\nDaily content",
                "tags": ["daily"],
                "frontmatter": {"date": "2026-03-08"},
            }
        )
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


def test_shared_operational_error_contract():
    from obsidian_brain.tools.errors import error_json

    error = CLINotFoundError()
    assert json.loads(error_json(error)) == {
        "error": True,
        "type": "CLINotFoundError",
        "message": str(error),
    }


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
        result = await server.call_tool(
            "create_note",
            {
                "path": "new/note.md",
                "content": "Hello world",
            },
        )
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

    @pytest.mark.parametrize(
        "current",
        [
            "A paragraph mentioning ## Notes inline.",
            "## Notes and more",
            "```markdown\n## Notes\n```",
            "~~~\n## Notes\n~~~",
        ],
    )
    @pytest.mark.anyio
    async def test_append_heading_ignores_false_positives(self, setup, current):
        server, client = setup
        client.get_note.return_value = {"content": current}

        await server.call_tool(
            "append_to_note",
            {"path": "test.md", "content": "New item", "heading": "## Notes"},
        )

        client.update_note.assert_awaited_once_with("test.md", f"{current}\n\n## Notes\n\nNew item")

    @pytest.mark.anyio
    async def test_append_heading_preserves_frontmatter_and_targets_real_heading(self, setup):
        server, client = setup
        body = "# Title\n\n```markdown\n## Notes\nfenced decoy\n```\n\n## Notes\nExisting item"
        raw = f"---\ntags:\n  - project\naliases:\n  - Project notes\n---\n{body}"
        client.get_note.return_value = {"content": body, "raw": raw}

        await server.call_tool(
            "append_to_note",
            {"path": "test.md", "content": "New item", "heading": "## Notes"},
        )

        client.update_note.assert_awaited_once_with(
            "test.md",
            "---\n"
            "tags:\n"
            "  - project\n"
            "aliases:\n"
            "  - Project notes\n"
            "---\n"
            "# Title\n\n"
            "```markdown\n## Notes\nfenced decoy\n```\n\n"
            "## Notes\nNew item\nExisting item",
        )

    @pytest.mark.parametrize(
        "existing",
        [
            "## Notes",
            "  ## Notes",
            "## Notes ##",
            "##   Notes   ",
        ],
    )
    @pytest.mark.anyio
    async def test_append_heading_matches_valid_atx_variants(self, setup, existing):
        """Indented, padded and closed ATX forms are the same heading."""
        server, client = setup
        current = f"# Title\n\n{existing}\nExisting item\n"
        client.get_note.return_value = {"content": current, "raw": current}

        await server.call_tool(
            "append_to_note",
            {"path": "test.md", "content": "New item", "heading": "## Notes"},
        )

        written = client.update_note.await_args[0][1]
        assert written.count("Notes") == 1
        assert written == f"# Title\n\n{existing}\nNew item\nExisting item\n"

    @pytest.mark.anyio
    async def test_writes_sync_cached_notes_and_remove_deletions(self, setup, monkeypatch):
        from obsidian_brain.tools import vault as vault_tools

        server, client = setup
        synced: list[str] = []
        invalidated: list[tuple[str, bool]] = []

        async def record_sync(sync_client, path: str) -> None:
            assert sync_client is client
            synced.append(path)

        async def record_invalidation(path: str, *, exists: bool) -> None:
            invalidated.append((path, exists))

        monkeypatch.setattr(
            vault_tools,
            "vault_cache",
            SimpleNamespace(
                sync_note=record_sync,
                invalidate_path=record_invalidation,
            ),
        )

        await server.call_tool("create_note", {"path": "created.md", "content": "Created"})
        await server.call_tool("update_note", {"path": "updated.md", "content": "Updated"})
        await server.call_tool("append_to_note", {"path": "appended.md", "content": "Appended"})
        await server.call_tool("delete_note", {"path": "deleted.md"})

        assert synced == ["created.md", "updated.md", "appended.md"]
        assert invalidated == [("deleted.md", False)]

    @pytest.mark.anyio
    async def test_update_note_refreshes_cached_tags_and_links(self, setup, monkeypatch):
        from obsidian_brain.cache import VaultCache
        from obsidian_brain.tools import vault as vault_tools

        server, client = setup
        state: dict[str, dict[str, Any]] = {
            "source.md": {
                "content": "# Source\n\n[[Old]]",
                "tags": ["old"],
                "frontmatter": {},
            },
            "Old.md": {"content": "# Old", "tags": [], "frontmatter": {}},
            "Target.md": {"content": "# Target", "tags": [], "frontmatter": {}},
        }
        client.get_all_files.return_value = list(state)

        async def get_note(path: str) -> dict[str, Any]:
            return state[path]

        async def update_note(path: str, content: str) -> None:
            state[path] = {
                "content": content,
                "tags": ["new"],
                "frontmatter": {},
            }

        client.get_note.side_effect = get_note
        client.update_note.side_effect = update_note
        cache = VaultCache()
        await cache.refresh(client)
        monkeypatch.setattr(vault_tools, "vault_cache", cache)

        result = await server.call_tool(
            "update_note",
            {"path": "source.md", "content": "# Source\n\n[[Target]]"},
        )

        assert _load_tool_result(result)["success"] is True
        source = cache.get_note_metadata("source.md")
        assert source is not None
        assert source.tags == ["new"]
        assert source.outgoing_links == ["Target"]
        assert cache.get_backlinks("Old.md") == []
        assert cache.get_backlinks("Target.md") == ["source.md"]

    @pytest.mark.parametrize(
        ("error", "error_type"),
        [
            (CLINotFoundError(), "CLINotFoundError"),
            (ObsidianNotRunningError(), "ObsidianNotRunningError"),
            (CLITimeoutError(1.0, ["obsidian", "files"]), "CLITimeoutError"),
            (
                ObsidianCLIError(2, "failed", ["obsidian", "files"]),
                "ObsidianCLIError",
            ),
        ],
    )
    @pytest.mark.anyio
    async def test_vault_serializes_operational_errors(self, setup, error, error_type):
        server, client = setup
        client.list_directory.side_effect = error

        result = await server.call_tool("list_vault_files", {"path": "/"})
        data = _load_tool_result(result)

        assert set(data) == {"error", "type", "message"}
        assert data["error"] is True
        assert data["type"] == error_type
        assert data["message"] == str(error)

    @pytest.mark.anyio
    async def test_vault_does_not_serialize_unexpected_errors(self, setup):
        server, client = setup
        client.list_directory.side_effect = RuntimeError("programming bug")

        with pytest.raises(ToolError, match="programming bug") as raised:
            await server.call_tool("list_vault_files", {"path": "/"})

        assert isinstance(raised.value.__cause__, RuntimeError)

    @pytest.mark.anyio
    async def test_list_vault_files(self, setup):
        server, client = setup
        result = await server.call_tool("list_vault_files", {"path": "/"})
        client.list_directory.assert_called_once()
        data = _load_tool_result(result)
        assert isinstance(data, list)
        assert len(data) == 2
        # The Obsidian CLI never returns folders -- every entry is a file,
        # regardless of what the (possibly stale) client reports.
        assert all(entry["type"] == "file" for entry in data)

    @pytest.mark.anyio
    async def test_list_vault_files_normalizes_stale_folder_type(self, setup):
        """The real CLI never returns folders; a stale client that still
        tags an entry "folder" must be normalized to "file" in the response."""
        server, client = setup
        client.list_directory.return_value = [{"name": "Areas", "type": "folder"}]

        result = await server.call_tool("list_vault_files", {"path": "/"})
        data = _load_tool_result(result)

        assert data == [{"name": "Areas", "type": "file"}]

    @pytest.mark.anyio
    async def test_create_note_reports_actual_deduped_path(self, setup, monkeypatch):
        """Obsidian dedupes an existing target instead of overwriting it; the
        response must report the actual created path, not the requested one."""
        from obsidian_brain.tools import vault as vault_tools

        server, client = setup
        client.create_note = AsyncMock(return_value="Note 1.md")
        synced: list[str] = []

        async def record_sync(sync_client, path: str) -> None:
            assert sync_client is client
            synced.append(path)

        monkeypatch.setattr(vault_tools, "vault_cache", SimpleNamespace(sync_note=record_sync))

        result = await server.call_tool(
            "create_note", {"path": "Note.md", "content": "Hello world"}
        )
        data = _load_tool_result(result)

        assert data["success"] is True
        assert data["path"] == "Note 1.md"
        assert "Note.md" in data["message"]
        assert "Note 1.md" in data["message"]
        # The message must explicitly explain the dedupe, not just mention paths.
        assert "already existed" in data["message"]
        assert "deduped" in data["message"].lower()
        # The cache must be synced for the note Obsidian actually wrote.
        assert synced == ["Note 1.md"]


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
        assert data["total_matches"] == 2
        assert data["results"] == [
            {
                "path": "note1.md",
                "matches": ["first context", "second context"],
                "score": 1.0,
            }
        ]
        client.search_simple.assert_awaited_once_with("test")

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

    @pytest.mark.anyio
    async def test_search_schema_omits_unused_context_length(self, setup):
        server, _ = setup
        tool = next(tool for tool in await server.list_tools() if tool.name == "search_content")

        assert set(tool.inputSchema["properties"]) == {"query"}

    @pytest.mark.parametrize(
        ("error", "error_type"),
        [
            (CLINotFoundError(), "CLINotFoundError"),
            (ObsidianNotRunningError(), "ObsidianNotRunningError"),
            (
                CLITimeoutError(1.0, ["obsidian", "search:context"]),
                "CLITimeoutError",
            ),
            (
                ObsidianCLIError(2, "failed", ["obsidian", "search:context"]),
                "ObsidianCLIError",
            ),
        ],
    )
    @pytest.mark.anyio
    async def test_search_serializes_operational_errors(self, setup, error, error_type):
        server, client = setup
        client.search_simple.side_effect = error

        result = await server.call_tool("search_content", {"query": "test"})
        data = _load_tool_result(result)

        assert set(data) == {"error", "type", "message"}
        assert data["error"] is True
        assert data["type"] == error_type
        assert data["message"] == str(error)

    @pytest.mark.anyio
    async def test_search_does_not_serialize_unexpected_errors(self, setup):
        server, client = setup
        client.search_simple.side_effect = RuntimeError("programming bug")

        with pytest.raises(ToolError, match="programming bug") as raised:
            await server.call_tool("search_content", {"query": "test"})

        assert isinstance(raised.value.__cause__, RuntimeError)


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
        result = await server.call_tool(
            "append_to_daily",
            {
                "content": "Test entry",
                "date": "2026-03-08",
            },
        )
        client.append_daily.assert_called_once()
        data = _load_tool_result(result)
        assert data["success"] is True

    @pytest.mark.anyio
    async def test_daily_writes_sync_the_resolved_daily_note(self, setup, monkeypatch):
        server, client = setup
        synced: list[str] = []

        async def _sync_note(_client, path: str) -> None:
            synced.append(path)

        monkeypatch.setattr("obsidian_brain.tools.daily.vault_cache.sync_note", _sync_note)

        await server.call_tool("append_to_daily", {"content": "Test entry", "date": "2026-03-08"})
        await server.call_tool("create_daily_entry", {"content": "Logged", "date": "2026-03-08"})

        assert synced == ["Daily/2026-03-08.md", "Daily/2026-03-08.md"]
        assert client.get_daily_path.await_count == 2
