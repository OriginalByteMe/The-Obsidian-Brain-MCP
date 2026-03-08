"""Tests for ObsidianCLIClient with mocked subprocess."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from obsidian_brain.cli_client import ObsidianCLIClient, find_cli_binary
from obsidian_brain.exceptions import (
    CLINotFoundError,
    CLITimeoutError,
    NoteNotFoundError,
    ObsidianCLIError,
)
from obsidian_brain.protocol import VaultClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_process(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Create a mock asyncio subprocess Process."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(
        return_value=(stdout.encode(), stderr.encode())
    )
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


# ---------------------------------------------------------------------------
# Binary Detection
# ---------------------------------------------------------------------------


class TestFindCliBinary:
    """Tests for CLI binary detection."""

    def test_finds_binary_via_env_var(self, tmp_path):
        """Should use OBSIDIAN_CLI_PATH env var if set."""
        fake_binary = tmp_path / "obsidian"
        fake_binary.touch()
        fake_binary.chmod(0o755)

        with patch.dict(os.environ, {"OBSIDIAN_CLI_PATH": str(fake_binary)}):
            result = find_cli_binary()
            assert result == str(fake_binary)

    def test_finds_binary_via_which(self):
        """Should fall back to shutil.which."""
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("obsidian_brain.cli_client.shutil.which", return_value="/usr/bin/obsidian"),
        ):
            # Remove env var if present
            os.environ.pop("OBSIDIAN_CLI_PATH", None)
            result = find_cli_binary()
            assert result == "/usr/bin/obsidian"

    def test_raises_cli_not_found_error(self):
        """Should raise CLINotFoundError when binary not found."""
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("obsidian_brain.cli_client.shutil.which", return_value=None),
        ):
            os.environ.pop("OBSIDIAN_CLI_PATH", None)
            with pytest.raises(CLINotFoundError):
                find_cli_binary()

    def test_env_var_path_not_found(self, tmp_path):
        """Should raise CLINotFoundError when env var path doesn't exist."""
        with patch.dict(os.environ, {"OBSIDIAN_CLI_PATH": "/nonexistent/obsidian"}):
            with pytest.raises(CLINotFoundError):
                find_cli_binary()


# ---------------------------------------------------------------------------
# _run method
# ---------------------------------------------------------------------------


class TestRunMethod:
    """Tests for the core _run subprocess method."""

    @pytest.fixture
    def client(self):
        """Create a CLI client with a fake binary path."""
        return ObsidianCLIClient(cli_path="/usr/bin/obsidian")

    @pytest.mark.asyncio
    async def test_successful_run(self, client):
        """Should return stdout on successful command."""
        proc = _make_mock_process(stdout="output text")
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            result = await client._run("version")
            assert result == "output text"

    @pytest.mark.asyncio
    async def test_non_zero_exit_raises_cli_error(self, client):
        """Should raise ObsidianCLIError on non-zero exit code."""
        proc = _make_mock_process(stderr="error msg", returncode=1)
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(ObsidianCLIError) as exc_info:
                await client._run("bad-command")
            assert exc_info.value.returncode == 1
            assert "error msg" in exc_info.value.stderr

    @pytest.mark.asyncio
    async def test_timeout_raises_cli_timeout_error(self, client):
        """Should raise CLITimeoutError when command times out."""
        proc = _make_mock_process()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(CLITimeoutError) as exc_info:
                await client._run("slow-cmd", timeout=1.0)
            assert exc_info.value.timeout == 1.0
            proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_list_form_exec(self, client):
        """Should pass args as list to create_subprocess_exec (no shell=True)."""
        proc = _make_mock_process(stdout="ok")
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await client._run("read", 'path="test.md"', "format=json")
            # First arg should be the binary, rest are command args
            call_args = mock_exec.call_args[0]
            assert call_args[0] == "/usr/bin/obsidian"
            assert "read" in call_args


# ---------------------------------------------------------------------------
# _run_json method
# ---------------------------------------------------------------------------


class TestRunJsonMethod:
    """Tests for the _run_json JSON parsing method."""

    @pytest.fixture
    def client(self):
        return ObsidianCLIClient(cli_path="/usr/bin/obsidian")

    @pytest.mark.asyncio
    async def test_parses_json_output(self, client):
        """Should parse JSON from stdout."""
        data = {"key": "value"}
        proc = _make_mock_process(stdout=json.dumps(data))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            result = await client._run_json("tags")
            assert result == data


# ---------------------------------------------------------------------------
# VaultClient method implementations
# ---------------------------------------------------------------------------


class TestVaultClientMethods:
    """Tests for each VaultClient Protocol method implementation."""

    @pytest.fixture
    def client(self):
        return ObsidianCLIClient(cli_path="/usr/bin/obsidian")

    @pytest.mark.asyncio
    async def test_get_note(self, client):
        """Should call obsidian read with path and format=json."""
        note_data = {
            "path": "test.md",
            "content": "# Test",
            "tags": ["test"],
            "frontmatter": {},
            "modified": None,
        }
        proc = _make_mock_process(stdout=json.dumps(note_data))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await client.get_note("test.md")
            assert result["path"] == "test.md"
            assert result["content"] == "# Test"
            # Verify CLI command structure
            call_args = mock_exec.call_args[0]
            assert "read" in call_args

    @pytest.mark.asyncio
    async def test_note_exists_true(self, client):
        """Should return True when note exists."""
        proc = _make_mock_process(stdout=json.dumps({"content": "hi"}))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            assert await client.note_exists("test.md") is True

    @pytest.mark.asyncio
    async def test_note_exists_false(self, client):
        """Should return False when note doesn't exist."""
        proc = _make_mock_process(stderr="not found", returncode=1)
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            assert await client.note_exists("missing.md") is False

    @pytest.mark.asyncio
    async def test_create_note(self, client):
        """Should call obsidian create with name, path, content, --silent."""
        proc = _make_mock_process(stdout="")
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await client.create_note("folder/note.md", "# Content")
            call_args = mock_exec.call_args[0]
            assert "create" in call_args
            assert "--silent" in call_args

    @pytest.mark.asyncio
    async def test_update_note(self, client):
        """Should call obsidian create with --overwrite --silent."""
        proc = _make_mock_process(stdout="")
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await client.update_note("folder/note.md", "# Updated")
            call_args = mock_exec.call_args[0]
            assert "create" in call_args
            assert "--overwrite" in call_args
            assert "--silent" in call_args

    @pytest.mark.asyncio
    async def test_append_to_note(self, client):
        """Should call obsidian append with file and content."""
        proc = _make_mock_process(stdout="")
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await client.append_to_note("note.md", "appended text")
            call_args = mock_exec.call_args[0]
            assert "append" in call_args

    @pytest.mark.asyncio
    async def test_delete_note(self, client):
        """Should call obsidian delete with file."""
        proc = _make_mock_process(stdout="")
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await client.delete_note("note.md")
            call_args = mock_exec.call_args[0]
            assert "delete" in call_args

    @pytest.mark.asyncio
    async def test_list_directory(self, client):
        """Should call obsidian files with folder arg."""
        file_list = [
            {"name": "note.md", "type": "file"},
            {"name": "subfolder", "type": "folder"},
        ]
        proc = _make_mock_process(stdout=json.dumps(file_list))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await client.list_directory("Projects")
            assert len(result) == 2
            call_args = mock_exec.call_args[0]
            assert "files" in call_args

    @pytest.mark.asyncio
    async def test_get_all_files(self, client):
        """Should call obsidian files with ext=md."""
        files = ["file1.md", "folder/file2.md"]
        proc = _make_mock_process(stdout=json.dumps(files))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await client.get_all_files()
            assert len(result) == 2
            call_args = mock_exec.call_args[0]
            assert "files" in call_args

    @pytest.mark.asyncio
    async def test_search_simple(self, client):
        """Should call obsidian search with query."""
        results = [{"path": "test.md", "matches": ["hit"], "score": 1.0}]
        proc = _make_mock_process(stdout=json.dumps(results))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await client.search_simple("test query")
            assert len(result) == 1
            call_args = mock_exec.call_args[0]
            assert "search" in call_args

    @pytest.mark.asyncio
    async def test_get_daily_note(self, client):
        """Should call obsidian daily:read."""
        daily = {"content": "# Today", "tags": [], "frontmatter": {}}
        proc = _make_mock_process(stdout=json.dumps(daily))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await client.get_daily_note()
            assert result["content"] == "# Today"
            call_args = mock_exec.call_args[0]
            assert "daily:read" in call_args

    @pytest.mark.asyncio
    async def test_append_daily(self, client):
        """Should call obsidian daily:append with content."""
        proc = _make_mock_process(stdout="")
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await client.append_daily("new entry")
            call_args = mock_exec.call_args[0]
            assert "daily:append" in call_args

    @pytest.mark.asyncio
    async def test_get_tags(self, client):
        """Should call obsidian tags format=json."""
        tags = {"project": 5, "daily": 10}
        proc = _make_mock_process(stdout=json.dumps(tags))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await client.get_tags()
            assert result["project"] == 5
            call_args = mock_exec.call_args[0]
            assert "tags" in call_args

    @pytest.mark.asyncio
    async def test_get_backlinks(self, client):
        """Should call obsidian backlinks with file."""
        links = ["other.md", "ref.md"]
        proc = _make_mock_process(stdout=json.dumps(links))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await client.get_backlinks("note.md")
            assert len(result) == 2
            call_args = mock_exec.call_args[0]
            assert "backlinks" in call_args

    @pytest.mark.asyncio
    async def test_get_links(self, client):
        """Should call obsidian links with file."""
        links = ["linked1.md", "linked2.md"]
        proc = _make_mock_process(stdout=json.dumps(links))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await client.get_links("note.md")
            assert len(result) == 2
            call_args = mock_exec.call_args[0]
            assert "links" in call_args


# ---------------------------------------------------------------------------
# Path Sanitization
# ---------------------------------------------------------------------------


class TestPathSanitization:
    """Tests for path validation and sanitization."""

    @pytest.fixture
    def client(self):
        return ObsidianCLIClient(cli_path="/usr/bin/obsidian")

    @pytest.mark.asyncio
    async def test_rejects_null_bytes_in_path(self, client):
        """Should reject paths containing null bytes."""
        with pytest.raises(ValueError, match="null"):
            await client.get_note("bad\x00path.md")

    @pytest.mark.asyncio
    async def test_allows_normal_paths(self, client):
        """Should accept normal paths with spaces and unicode."""
        proc = _make_mock_process(stdout=json.dumps({"content": "ok"}))
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            # These should not raise
            await client.get_note("My Notes/Project Name.md")
            await client.get_note("Notes/Cafe.md")


# ---------------------------------------------------------------------------
# Protocol Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Test that ObsidianCLIClient satisfies VaultClient Protocol."""

    def test_isinstance_check(self):
        """ObsidianCLIClient should pass isinstance check for VaultClient."""
        client = ObsidianCLIClient(cli_path="/usr/bin/obsidian")
        assert isinstance(client, VaultClient)
