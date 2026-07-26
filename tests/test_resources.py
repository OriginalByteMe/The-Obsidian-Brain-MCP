"""Protocol-level tests for vault resources."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextResourceContents
from pydantic import AnyUrl

from obsidian_brain.cache import vault_cache
from obsidian_brain.exceptions import NoteNotFoundError
from obsidian_brain.models import NoteMetadata, VaultStructure


class FakeNoteClient:
    """Deterministic note reader used behind the real in-memory MCP session."""

    def __init__(self) -> None:
        self.notes: dict[str, str] = {
            "Inbox.md": "# Inbox\n",
            "Projects/Nested Plan.md": (
                "---\ntags:\n  - project\naliases:\n  - Plan\n---\n# Nested Plan\n\nShip it.\n"
            ),
            "Hidden.md": "# Not in the cache\n",
            "Obsidian Brain/knowledge-base.md": "# Knowledge Base\n\nGenerated content.\n",
        }
        self.read_paths: list[str] = []

    async def get_note(self, path: str) -> dict[str, object]:
        self.read_paths.append(path)
        if path not in self.notes:
            raise NoteNotFoundError(path)
        raw = self.notes[path]
        # Mirror the real client: body in `content`, whole file in `raw`.
        body = raw.split("---\n", 2)[-1] if raw.startswith("---\n") else raw
        return {"path": path, "content": body, "raw": raw}


@pytest.fixture
async def connected_resource_session(monkeypatch: pytest.MonkeyPatch):
    from obsidian_brain.server import client, mcp

    structure = VaultStructure(
        notes=[
            NoteMetadata(path="Projects/Nested Plan.md", title="Nested Plan"),
            NoteMetadata(path="Inbox.md", title="Inbox"),
        ],
        refreshed_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    fake_client = FakeNoteClient()
    monkeypatch.setattr(vault_cache, "_structure", structure)
    monkeypatch.setattr(
        vault_cache,
        "_file_paths",
        [
            "Projects/Nested Plan.md",
            "Inbox.md",
            "Assets/cover.PNG",
            "Boards/plan.canvas",
            "config.yml",
        ],
        raising=False,
    )
    monkeypatch.setattr(client, "get_note", fake_client.get_note)

    ready = asyncio.get_running_loop().create_future()
    stop = asyncio.Event()

    async def connect() -> None:
        try:
            async with create_connected_server_and_client_session(mcp) as session:
                ready.set_result(session)
                await stop.wait()
        except BaseException as error:
            if not ready.done():
                ready.set_exception(error)
            else:
                raise

    task = asyncio.create_task(connect())
    try:
        yield await ready, fake_client
    finally:
        stop.set()
        await task


@pytest.mark.asyncio
async def test_note_index_requests_refresh_when_cache_is_uninitialized(
    monkeypatch: pytest.MonkeyPatch,
):
    from obsidian_brain.server import mcp

    monkeypatch.setattr(vault_cache, "_structure", None)
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.read_resource(AnyUrl("vault://files"))
    content = result.contents[0]
    assert isinstance(content, TextResourceContents)
    assert json.loads(content.text) == {
        "error": "Call refresh_vault_structure to initialize or update this cached index."
    }


@pytest.mark.asyncio
async def test_lists_note_index_and_read_template_over_protocol(
    connected_resource_session,
):
    (session, _client) = connected_resource_session
    resources = (await session.list_resources()).resources
    files_resource = next(item for item in resources if str(item.uri) == "vault://files")
    assert files_resource.mimeType == "application/json"
    assert "refresh_vault_structure" in (files_resource.description or "")

    templates = (await session.list_resource_templates()).resourceTemplates
    note_template = next(item for item in templates if item.uriTemplate == "vault://note/{path}")
    assert note_template.mimeType == "text/markdown"


@pytest.mark.asyncio
async def test_reads_cached_index_and_nested_note_over_protocol(
    connected_resource_session,
):
    (session, client) = connected_resource_session
    index_result = await session.read_resource(AnyUrl("vault://files"))
    index_content = index_result.contents[0]
    assert isinstance(index_content, TextResourceContents)
    index = json.loads(index_content.text)
    assert index == {
        "files": [
            {
                "path": "Assets/cover.PNG",
                "extension": ".png",
                "readable": False,
            },
            {
                "path": "Boards/plan.canvas",
                "extension": ".canvas",
                "readable": False,
            },
            {
                "path": "Inbox.md",
                "extension": ".md",
                "readable": True,
                "uri": "vault://note/Inbox.md",
            },
            {
                "path": "Projects/Nested Plan.md",
                "extension": ".md",
                "readable": True,
                "uri": "vault://note/Projects%2FNested%20Plan.md",
            },
            {
                "path": "config.yml",
                "extension": ".yml",
                "readable": False,
            },
        ],
        "refreshed_at": "2026-01-02T03:04:05+00:00",
        "refresh": "Call refresh_vault_structure to initialize or update this cached index.",
    }

    note_result = await session.read_resource(AnyUrl("vault://note/Projects%2FNested%20Plan.md"))
    note_content = note_result.contents[0]
    assert isinstance(note_content, TextResourceContents)
    # The resource must serve the file verbatim, frontmatter included.
    assert note_content.text == (
        "---\ntags:\n  - project\naliases:\n  - Plan\n---\n# Nested Plan\n\nShip it.\n"
    )
    assert note_content.mimeType == "text/markdown"
    assert client.read_paths == ["Projects/Nested Plan.md"]


@pytest.mark.asyncio
async def test_reads_knowledge_base_resource_from_expected_path(
    connected_resource_session,
):
    """vault://knowledge must read the same fixed, CLI-writable .md path
    that create_vault_knowledge_base/get_knowledge_base_status use."""
    from obsidian_brain.knowledge import KNOWLEDGE_BASE_PATH

    assert KNOWLEDGE_BASE_PATH == "Obsidian Brain/knowledge-base.md"

    (session, client) = connected_resource_session
    result = await session.read_resource(AnyUrl("vault://knowledge"))
    content = result.contents[0]
    assert isinstance(content, TextResourceContents)
    assert content.text == "# Knowledge Base\n\nGenerated content.\n"
    assert client.read_paths == ["Obsidian Brain/knowledge-base.md"]


@pytest.mark.asyncio
async def test_invalidated_note_stays_indexed_and_reads_live_content(
    connected_resource_session,
):
    (session, client) = connected_resource_session
    await vault_cache.invalidate_path("Inbox.md", exists=True)

    index_result = await session.read_resource(AnyUrl("vault://files"))
    index_content = index_result.contents[0]
    assert isinstance(index_content, TextResourceContents)
    paths = [entry["path"] for entry in json.loads(index_content.text)["files"]]
    assert "Inbox.md" in paths

    note_result = await session.read_resource(AnyUrl("vault://note/Inbox.md"))
    note_content = note_result.contents[0]
    assert isinstance(note_content, TextResourceContents)
    assert note_content.text == "# Inbox\n"
    assert client.read_paths == ["Inbox.md"]


@pytest.mark.asyncio
async def test_reads_valid_markdown_path_without_cached_metadata(
    connected_resource_session,
):
    (session, client) = connected_resource_session
    result = await session.read_resource(AnyUrl("vault://note/Hidden.md"))
    content = result.contents[0]
    assert isinstance(content, TextResourceContents)
    assert content.text == "# Not in the cache\n"
    assert client.read_paths == ["Hidden.md"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "uri",
    [
        "vault://note/%2E%2E%2Fsecret.md",
        "vault://note/config.yml",
    ],
)
async def test_rejects_unsafe_or_non_markdown_note_resources(
    connected_resource_session,
    uri: str,
):
    (session, client) = connected_resource_session
    with pytest.raises(McpError):
        _ = await session.read_resource(AnyUrl(uri))
    assert client.read_paths == []


@pytest.mark.asyncio
async def test_missing_note_error_comes_from_live_client(
    connected_resource_session,
):
    (session, client) = connected_resource_session
    with pytest.raises(McpError):
        _ = await session.read_resource(AnyUrl("vault://note/Missing.md"))
    assert client.read_paths == ["Missing.md"]
