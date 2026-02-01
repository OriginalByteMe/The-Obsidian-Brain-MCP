"""Tests for vault access resources."""

import json

import pytest
from pytest_httpx import HTTPXMock

from obsidian_brain.resources.vault_access import register_vault_access_resources
from obsidian_brain.cache import vault_cache, VaultCache
from obsidian_brain.models import NoteMetadata, VaultStructure, VaultStats


class MockServer:
    """Mock MCP server for testing."""

    def __init__(self):
        self.resources = {}

    def resource(self, uri: str, mime_type: str = "text/plain"):
        def decorator(func):
            self.resources[uri] = func
            return func
        return decorator


@pytest.fixture
def mock_server():
    """Create a mock server with registered resources."""
    server = MockServer()
    register_vault_access_resources(server)
    return server


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("OBSIDIAN_API_KEY", "test-key")
    monkeypatch.setenv("OBSIDIAN_HOST", "127.0.0.1")
    monkeypatch.setenv("OBSIDIAN_PORT", "27124")


@pytest.fixture
def reset_cache():
    """Reset the vault cache before each test."""
    vault_cache._structure = None
    vault_cache._backlink_index = {}
    yield
    vault_cache._structure = None
    vault_cache._backlink_index = {}


class TestNoteResource:
    """Tests for vault://note/{path} resource (FR2)."""

    async def test_returns_note_content(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Verify note resource returns note content."""
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/Projects/MyNote.md",
            text="# My Note\n\nContent here",
        )

        get_vault_note = mock_server.resources["vault://note/{path:path}"]
        result = await get_vault_note("Projects/MyNote.md")

        assert result == "# My Note\n\nContent here"

    async def test_handles_not_found(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Verify graceful error for missing notes."""
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/NonExistent.md",
            status_code=404,
        )

        get_vault_note = mock_server.resources["vault://note/{path:path}"]
        result = await get_vault_note("NonExistent.md")

        assert "Error: Note Not Found" in result
        assert "NonExistent.md" in result

    async def test_handles_api_error(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Verify graceful handling of API errors."""
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/test.md",
            status_code=500,
            json={"message": "Internal server error"},
        )

        get_vault_note = mock_server.resources["vault://note/{path:path}"]
        result = await get_vault_note("test.md")

        assert "Error: API Error" in result


class TestFolderResource:
    """Tests for vault://folder/{path} resource (FR3)."""

    async def test_lists_folder_via_api(
        self, mock_server, mock_env, reset_cache, httpx_mock: HTTPXMock
    ):
        """Verify folder resource lists notes via API when cache not initialized."""
        # List directory response
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/Projects/",
            json={"files": ["note1.md", "note2.md", "subfolder/"]},
        )
        # Subfolder response
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/Projects/subfolder/",
            json={"files": ["nested.md"]},
        )
        # Note metadata responses
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/Projects/note1.md",
            json={"content": "# Note 1", "tags": ["project"], "frontmatter": {}},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/Projects/note2.md",
            json={"content": "# Note 2", "tags": ["project"], "frontmatter": {}},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/Projects/subfolder/nested.md",
            json={"content": "# Nested", "tags": [], "frontmatter": {}},
        )

        get_vault_folder = mock_server.resources["vault://folder/{path:path}"]
        result = await get_vault_folder("Projects")
        data = json.loads(result)

        assert data["folder"] == "Projects"
        assert data["total_notes"] == 3
        assert len(data["notes"]) == 3
        assert "Projects/subfolder" in data["subfolders"]

    async def test_uses_cache_when_initialized(
        self, mock_server, mock_env, reset_cache
    ):
        """Verify folder resource uses cache when available."""
        # Set up cache with test data
        vault_cache._structure = VaultStructure(
            folders=[],
            notes=[
                NoteMetadata(
                    path="Projects/note1.md",
                    title="Note 1",
                    tags=["project"],
                    outgoing_links=[],
                    incoming_links=[],
                ),
                NoteMetadata(
                    path="Projects/subfolder/note2.md",
                    title="Note 2",
                    tags=["project"],
                    outgoing_links=[],
                    incoming_links=[],
                ),
                NoteMetadata(
                    path="Other/note3.md",
                    title="Note 3",
                    tags=[],
                    outgoing_links=[],
                    incoming_links=[],
                ),
            ],
            stats=VaultStats(
                total_notes=3,
                total_folders=3,
                total_tags=1,
                total_links=0,
                orphan_notes=3,
            ),
        )

        get_vault_folder = mock_server.resources["vault://folder/{path:path}"]
        result = await get_vault_folder("Projects")
        data = json.loads(result)

        # Should only return Projects notes
        assert data["folder"] == "Projects"
        assert data["total_notes"] == 2
        paths = [n["path"] for n in data["notes"]]
        assert "Projects/note1.md" in paths
        assert "Projects/subfolder/note2.md" in paths
        assert "Other/note3.md" not in paths
        # Should detect subfolder
        assert "Projects/subfolder" in data["subfolders"]

    async def test_handles_api_error(
        self, mock_server, mock_env, reset_cache, httpx_mock: HTTPXMock
    ):
        """Verify graceful handling of API errors."""
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/BadFolder/",
            status_code=500,
            json={"message": "Internal error"},
        )

        get_vault_folder = mock_server.resources["vault://folder/{path:path}"]
        result = await get_vault_folder("BadFolder")
        data = json.loads(result)

        assert data["error"] is True
        assert "Failed to list folder" in data["message"]

    async def test_empty_folder(
        self, mock_server, mock_env, reset_cache, httpx_mock: HTTPXMock
    ):
        """Verify empty folder handling."""
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/EmptyFolder/",
            json={"files": []},
        )

        get_vault_folder = mock_server.resources["vault://folder/{path:path}"]
        result = await get_vault_folder("EmptyFolder")
        data = json.loads(result)

        assert data["folder"] == "EmptyFolder"
        assert data["total_notes"] == 0
        assert data["notes"] == []
        assert data["subfolders"] == []
