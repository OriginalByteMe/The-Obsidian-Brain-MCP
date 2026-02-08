"""Tests for session tracking tools."""

import json
import re

import pytest
from pytest_httpx import HTTPXMock

from obsidian_brain.tools.session import register_session_tools


class MockServer:
    """Mock MCP server for testing."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator


@pytest.fixture
def mock_server():
    """Create a mock server with registered session tools."""
    server = MockServer()
    register_session_tools(server)
    return server


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("OBSIDIAN_API_KEY", "test-key")
    monkeypatch.setenv("OBSIDIAN_HOST", "127.0.0.1")
    monkeypatch.setenv("OBSIDIAN_PORT", "27124")


CONFIG_URL = "https://127.0.0.1:27124/vault/Obsidian Brain/config.yml"
SEARCH_URL_PATTERN = re.compile(r"https://127\.0\.0\.1:27124/search/simple/\?.*")


class TestGetBrainConfig:
    """Tests for get_brain_config tool."""

    async def test_returns_defaults_when_no_config(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """When config file doesn't exist, return defaults."""
        httpx_mock.add_response(
            method="GET",
            url=CONFIG_URL,
            status_code=404,
        )

        result = await mock_server.tools["get_brain_config"]()
        data = json.loads(result)

        assert data["success"] is True
        assert data["source"] == "defaults"
        assert data["config"]["autonomy"]["session_start_context"] == "silent"
        assert data["config"]["autonomy"]["brag_doc_update"] == "prompt"
        assert data["config"]["plugin"]["checkin_interval_minutes"] == 30

    async def test_merges_vault_config_with_defaults(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """When vault config exists, merge with defaults."""
        httpx_mock.add_response(
            method="GET",
            url=CONFIG_URL,
            text="version: '1.0'\nautonomy:\n  brag_doc_update: disabled\n",
        )

        result = await mock_server.tools["get_brain_config"]()
        data = json.loads(result)

        assert data["success"] is True
        assert data["source"] == "vault"
        # Overridden value
        assert data["config"]["autonomy"]["brag_doc_update"] == "disabled"
        # Default values still present
        assert data["config"]["autonomy"]["session_start_context"] == "silent"
        assert data["config"]["plugin"]["checkin_interval_minutes"] == 30


class TestUpdateBrainConfig:
    """Tests for update_brain_config tool."""

    async def test_updates_dot_notation_key(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Updating a dot-notation key writes back to vault."""
        # Read existing config
        httpx_mock.add_response(
            method="GET",
            url=CONFIG_URL,
            text="version: '1.0'\nautonomy:\n  brag_doc_update: prompt\n",
        )
        # Write updated config
        httpx_mock.add_response(
            method="PUT",
            url=CONFIG_URL,
            status_code=200,
        )

        result = await mock_server.tools["update_brain_config"](
            "autonomy.brag_doc_update", "silent"
        )
        data = json.loads(result)

        assert data["success"] is True
        assert data["key"] == "autonomy.brag_doc_update"
        assert data["value"] == "silent"

    async def test_creates_config_when_missing(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Creates config file if it doesn't exist."""
        httpx_mock.add_response(
            method="GET",
            url=CONFIG_URL,
            status_code=404,
        )
        httpx_mock.add_response(
            method="PUT",
            url=CONFIG_URL,
            status_code=200,
        )

        result = await mock_server.tools["update_brain_config"](
            "plugin.checkin_interval_minutes", "45"
        )
        data = json.loads(result)

        assert data["success"] is True


class TestGetSessionState:
    """Tests for get_session_state tool."""

    async def test_returns_defaults_for_new_session(self, mock_server, mock_env):
        """Returns default state when no session file exists."""
        result = await mock_server.tools["get_session_state"]()
        data = json.loads(result)

        assert data["success"] is True
        assert "state" in data
        assert data["state"]["notes_created"] == []
        assert data["state"]["daily_entries"] == []
        assert data["state"]["brag_entries"] == []


class TestRecordSessionActivity:
    """Tests for record_session_activity tool."""

    async def test_records_activity(self, mock_server, mock_env):
        """Records an activity in session state."""
        result = await mock_server.tools["record_session_activity"](
            "note_created", "Created learning note about auth", ["Learning/Auth.md"]
        )
        data = json.loads(result)

        assert data["success"] is True
        assert data["activity_type"] == "note_created"
        assert "auth" in data["summary"].lower()
        assert data["note_paths"] == ["Learning/Auth.md"]

    async def test_does_not_duplicate_note_paths(self, mock_server, mock_env):
        """Recording the same note path twice should not duplicate."""
        await mock_server.tools["record_session_activity"](
            "note_created", "First", ["Learning/Auth.md"]
        )
        await mock_server.tools["record_session_activity"](
            "note_created", "Second", ["Learning/Auth.md"]
        )

        result = await mock_server.tools["get_session_state"]()
        data = json.loads(result)

        # The in-process state should have the note path only once
        notes = data["state"]["notes_created"]
        assert notes.count("Learning/Auth.md") == 1


class TestAppendToBragDoc:
    """Tests for append_to_brag_doc tool."""

    async def test_creates_brag_doc_when_missing(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Creates brag doc if it doesn't exist."""
        # Config read
        httpx_mock.add_response(
            method="GET",
            url=CONFIG_URL,
            status_code=404,
        )
        # Search for existing brag doc
        httpx_mock.add_response(
            method="POST",
            url=SEARCH_URL_PATTERN,
            json=[],
        )
        # Brag doc doesn't exist
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/Obsidian Brain/Brag Doc.md",
            status_code=404,
        )
        # Create brag doc
        httpx_mock.add_response(
            method="PUT",
            url="https://127.0.0.1:27124/vault/Obsidian Brain/Brag Doc.md",
            status_code=200,
        )

        result = await mock_server.tools["append_to_brag_doc"](
            "Features Built", "Implemented auth system", ["Auth Design"]
        )
        data = json.loads(result)

        assert data["success"] is True
        assert data["action"] == "appended"
        assert data["category"] == "Features Built"

    async def test_skips_duplicate_entry(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Skips entry if description already exists in brag doc."""
        # Config read
        httpx_mock.add_response(
            method="GET",
            url=CONFIG_URL,
            status_code=404,
        )
        # Search for existing brag doc
        httpx_mock.add_response(
            method="POST",
            url=SEARCH_URL_PATTERN,
            json=[],
        )
        # Brag doc exists with the entry already
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/Obsidian Brain/Brag Doc.md",
            text="## Features Built\n\n- **2026-02-08**: Implemented auth system\n",
        )

        result = await mock_server.tools["append_to_brag_doc"](
            "Features Built", "Implemented auth system"
        )
        data = json.loads(result)

        assert data["success"] is True
        assert data["action"] == "skipped"
