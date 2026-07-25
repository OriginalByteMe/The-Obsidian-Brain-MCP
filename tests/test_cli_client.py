"""Tests for ObsidianCLIClient with mocked subprocess."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from obsidian_brain.cli_client import (
    ObsidianCLIClient,
    _check_obsidian_running,
    find_cli_binary,
)
from obsidian_brain.exceptions import (
    CLINotFoundError,
    CLITimeoutError,
    NoteNotFoundError,
    ObsidianCLIError,
    ObsidianNotRunningError,
)
from obsidian_brain.protocol import VaultClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_process(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Create a mock asyncio subprocess Process."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


# ---------------------------------------------------------------------------
# Auto-patch: skip Obsidian-running check in all tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _skip_obsidian_running_check(monkeypatch):
    """Bypass the pre-flight check that requires a running Obsidian instance."""
    monkeypatch.setattr("obsidian_brain.cli_client._obsidian_running_until", 0.0)

    async def no_op():
        return None

    with patch("obsidian_brain.cli_client._check_obsidian_running", new=no_op):
        yield


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    """Create an executable CLI double that records its real process argv."""
    executable = tmp_path / "obsidian"
    calls = tmp_path / "calls.jsonl"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['FAKE_OBSIDIAN_CALLS'], 'a', encoding='utf-8') as f:\n"
        "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.stdout.write(os.environ.get('FAKE_OBSIDIAN_STDOUT', ''))\n"
        "sys.stderr.write(os.environ.get('FAKE_OBSIDIAN_STDERR', ''))\n"
        "raise SystemExit(int(os.environ.get('FAKE_OBSIDIAN_EXIT', '0')))\n"
    )
    executable.chmod(0o755)
    monkeypatch.setenv("FAKE_OBSIDIAN_CALLS", str(calls))
    monkeypatch.delenv("FAKE_OBSIDIAN_STDOUT", raising=False)
    monkeypatch.delenv("FAKE_OBSIDIAN_STDERR", raising=False)
    monkeypatch.delenv("FAKE_OBSIDIAN_EXIT", raising=False)
    monkeypatch.delenv("OBSIDIAN_VAULT", raising=False)
    return str(executable), calls


def _captured_calls(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


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
# Obsidian running preflight
# ---------------------------------------------------------------------------


class TestObsidianRunningPreflight:
    @pytest.mark.asyncio
    async def test_repeated_cli_calls_detect_once_within_ttl(self):
        running = _make_mock_process(stdout="123\n")
        cli_call = _make_mock_process(stdout="ok")
        client = ObsidianCLIClient(cli_path="/usr/bin/obsidian")

        with (
            patch(
                "obsidian_brain.cli_client._check_obsidian_running",
                new=_check_obsidian_running,
            ),
            patch("obsidian_brain.cli_client._clock", return_value=100.0),
            patch(
                "obsidian_brain.cli_client.asyncio.create_subprocess_exec",
                side_effect=[running, cli_call, cli_call],
            ) as mock_exec,
        ):
            await client._run("version")
            await client._run("version")

        assert mock_exec.call_count == 3
        assert [call.args[0] for call in mock_exec.call_args_list].count("pgrep") == 1

    @pytest.mark.asyncio
    async def test_expired_detection_is_rechecked(self):
        now = 100.0
        running = _make_mock_process(stdout="123\n")

        with (
            patch("obsidian_brain.cli_client._clock", side_effect=lambda: now),
            patch(
                "obsidian_brain.cli_client.asyncio.create_subprocess_exec",
                return_value=running,
            ) as mock_exec,
        ):
            await _check_obsidian_running()
            now = 105.0
            await _check_obsidian_running()

        assert mock_exec.call_count == 2

    @pytest.mark.asyncio
    async def test_negative_detection_is_not_cached(self):
        stopped = _make_mock_process(returncode=1)

        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec",
            return_value=stopped,
        ) as mock_exec:
            with pytest.raises(ObsidianNotRunningError):
                await _check_obsidian_running()
            with pytest.raises(ObsidianNotRunningError):
                await _check_obsidian_running()

        assert mock_exec.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_pgrep_skips_without_caching(self):
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError,
        ) as mock_exec:
            await _check_obsidian_running()
            await _check_obsidian_running()

        assert mock_exec.call_count == 2

    @pytest.mark.asyncio
    async def test_hung_pgrep_skips_without_caching(self):
        hung = _make_mock_process()
        hung.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec",
            return_value=hung,
        ) as mock_exec:
            await _check_obsidian_running()
            await _check_obsidian_running()

        assert mock_exec.call_count == 2


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
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
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
        """Should call obsidian read with path and parse raw markdown."""
        raw_md = "---\ntags:\n- test\ntitle: Test Note\n---\n# Test"
        proc = _make_mock_process(stdout=raw_md)
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            result = await client.get_note("test.md")
            assert result["path"] == "test.md"
            assert result["content"] == "# Test"
            assert result["tags"] == ["test"]
            assert result["frontmatter"]["title"] == "Test Note"
            # Verify CLI command structure
            call_args = mock_exec.call_args[0]
            assert "read" in call_args
            # format=json should NOT be passed
            assert "format=json" not in call_args

    @pytest.mark.asyncio
    async def test_note_exists_true(self, client):
        """Should return True when note exists."""
        proc = _make_mock_process(stdout="# Hello")
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
        """Should target the exact vault-relative path."""
        proc = _make_mock_process(stdout="")
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            await client.create_note("folder/note.md", "# Content")
            call_args = mock_exec.call_args[0]
            assert "path=folder/note.md" in call_args
            assert not any(arg.startswith("name=") for arg in call_args)

    @pytest.mark.asyncio
    async def test_update_note(self, client):
        """Should target the exact path with the official overwrite flag."""
        proc = _make_mock_process(stdout="")
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            await client.update_note("folder/note.md", "# Updated")
            call_args = mock_exec.call_args[0]
            assert "path=folder/note.md" in call_args
            assert "overwrite" in call_args
            assert "--overwrite" not in call_args

    @pytest.mark.asyncio
    async def test_append_to_note(self, client):
        """Should call obsidian append with file and content."""
        proc = _make_mock_process(stdout="")
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            await client.append_to_note("note.md", "appended text")
            call_args = mock_exec.call_args[0]
            assert "append" in call_args

    @pytest.mark.asyncio
    async def test_delete_note(self, client):
        """Should call obsidian delete with file."""
        proc = _make_mock_process(stdout="")
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            await client.delete_note("note.md")
            call_args = mock_exec.call_args[0]
            assert "delete" in call_args

    @pytest.mark.asyncio
    async def test_list_directory(self, client):
        """Should call obsidian files with folder arg and parse plain text."""
        # The CLI files command returns plain text, one entry per line
        plain_output = "note.md\nsubfolder/\n"
        proc = _make_mock_process(stdout=plain_output)
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            result = await client.list_directory("Projects")
            assert len(result) == 2
            assert result[0] == {"name": "note.md", "type": "file"}
            assert result[1] == {"name": "subfolder", "type": "folder"}
            call_args = mock_exec.call_args[0]
            assert "files" in call_args

    @pytest.mark.asyncio
    async def test_get_all_files(self, client):
        """Should list every vault file without applying an extension filter."""
        plain_output = "file1.md\nfolder/file2.md\nassets/cover.png\nboard.canvas\n"
        proc = _make_mock_process(stdout=plain_output)
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            result = await client.get_all_files()
            assert result == [
                "file1.md",
                "folder/file2.md",
                "assets/cover.png",
                "board.canvas",
            ]
            call_args = mock_exec.call_args[0]
            assert "files" in call_args
            assert "ext=md" not in call_args

    @pytest.mark.asyncio
    async def test_search_simple(self, client):
        """Should call context search and parse its documented text output."""
        output = "test.md:7: matching line"
        proc = _make_mock_process(stdout=output)
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            result = await client.search_simple("test query")
            assert result == [{"path": "test.md", "matches": ["matching line"], "score": 0.0}]
            call_args = mock_exec.call_args[0]
            assert "search:context" in call_args
            assert "format=text" in call_args

    @pytest.mark.asyncio
    async def test_get_daily_note(self, client):
        """Should call obsidian daily:read and parse raw markdown."""
        raw_md = '---\ntags:\n- daily\ndate: "2026-03-08"\n---\n# Today'
        proc = _make_mock_process(stdout=raw_md)
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            result = await client.get_daily_note()
            assert result["content"] == "# Today"
            assert result["tags"] == ["daily"]
            call_args = mock_exec.call_args[0]
            assert "daily:read" in call_args
            assert "format=json" not in call_args

    @pytest.mark.asyncio
    async def test_append_daily(self, client):
        """Should call obsidian daily:append with content."""
        proc = _make_mock_process(stdout="")
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            await client.append_daily("new entry")
            call_args = mock_exec.call_args[0]
            assert "daily:append" in call_args

    @pytest.mark.asyncio
    async def test_get_tags(self, client):
        """Should call obsidian tags format=json."""
        tags = {"project": 5, "daily": 10}
        proc = _make_mock_process(stdout=json.dumps(tags))
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            result = await client.get_tags()
            assert result["project"] == 5
            call_args = mock_exec.call_args[0]
            assert "tags" in call_args

    @pytest.mark.asyncio
    async def test_get_backlinks(self, client):
        """Should call obsidian backlinks with file."""
        links = ["other.md", "ref.md"]
        proc = _make_mock_process(stdout=json.dumps(links))
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            result = await client.get_backlinks("note.md")
            assert len(result) == 2
            call_args = mock_exec.call_args[0]
            assert "backlinks" in call_args

    @pytest.mark.asyncio
    async def test_get_links(self, client):
        """Should call obsidian links with file."""
        links = ["linked1.md", "linked2.md"]
        proc = _make_mock_process(stdout=json.dumps(links))
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
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


class TestExecutableCLIContract:
    """Contract tests that execute a deterministic CLI double."""

    @pytest.mark.asyncio
    async def test_discovers_cli_lazily_and_puts_env_vault_before_command(
        self, fake_cli, monkeypatch
    ):
        executable, calls = fake_cli
        monkeypatch.setenv("OBSIDIAN_CLI_PATH", executable)
        monkeypatch.setenv("OBSIDIAN_VAULT", "Work Vault")
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", "# Note")

        client = ObsidianCLIClient()
        assert client.cli_path is None

        note = await client.get_note("Projects/Nested/Note.md")

        assert note["content"] == "# Note"
        assert client.cli_path == executable
        assert _captured_calls(calls) == [
            ["vault=Work Vault", "read", "path=Projects/Nested/Note.md"]
        ]

    @pytest.mark.asyncio
    async def test_missing_cli_is_reported_on_first_command_not_construction(
        self, tmp_path, monkeypatch
    ):
        missing = tmp_path / "missing-obsidian"
        monkeypatch.setenv("OBSIDIAN_CLI_PATH", str(missing))

        client = ObsidianCLIClient()

        with pytest.raises(CLINotFoundError):
            await client._run("version")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "arguments", "stdout", "expected"),
        [
            (
                "create_note",
                ("Projects/Nested/Note.md", "body"),
                "",
                ["create", "path=Projects/Nested/Note.md", "content=body"],
            ),
            (
                "update_note",
                ("Projects/Nested/Note.md", "body"),
                "",
                ["create", "path=Projects/Nested/Note.md", "content=body", "overwrite"],
            ),
            (
                "append_to_note",
                ("Projects/Nested/Note.md", "body"),
                "",
                ["append", "path=Projects/Nested/Note.md", "content=body"],
            ),
            (
                "delete_note",
                ("Projects/Nested/Note.md",),
                "",
                ["delete", "path=Projects/Nested/Note.md"],
            ),
            (
                "get_backlinks",
                ("Projects/Nested/Note.md",),
                "[]",
                ["backlinks", "path=Projects/Nested/Note.md", "format=json"],
            ),
            (
                "get_links",
                ("Projects/Nested/Note.md",),
                "[]",
                ["links", "path=Projects/Nested/Note.md", "format=json"],
            ),
        ],
    )
    async def test_nested_note_operations_pass_exact_paths(
        self, fake_cli, monkeypatch, method, arguments, stdout, expected
    ):
        executable, calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", stdout)
        client = ObsidianCLIClient(cli_path=executable)

        await getattr(client, method)(*arguments)

        assert _captured_calls(calls) == [expected]

    @pytest.mark.asyncio
    async def test_search_context_groups_grep_lines_by_path(self, fake_cli, monkeypatch):
        executable, calls = fake_cli
        monkeypatch.setenv(
            "FAKE_OBSIDIAN_STDOUT",
            "Projects/One.md:12: first hit\n"
            "Projects/One.md:19: second hit\n"
            "Other.md:3: another hit\n",
        )
        client = ObsidianCLIClient(cli_path=executable)

        result = await client.search_simple("needle")

        assert result == [
            {
                "path": "Projects/One.md",
                "matches": ["first hit", "second hit"],
                "score": 0.0,
            },
            {"path": "Other.md", "matches": ["another hit"], "score": 0.0},
        ]
        assert _captured_calls(calls) == [["search:context", "query=needle", "format=text"]]

    @pytest.mark.asyncio
    async def test_read_preserves_timestamped_note_content(self, fake_cli, monkeypatch):
        executable, _calls = fake_cli
        monkeypatch.setenv(
            "FAKE_OBSIDIAN_STDOUT",
            "2026-03-08 12:02:59 Loaded updated app package /tmp/app.asar\n"
            "2026-03-08 12:03:00 This is note content\n",
        )
        client = ObsidianCLIClient(cli_path=executable)

        note = await client.get_note("Journal.md")

        assert note["content"] == "2026-03-08 12:03:00 This is note content\n"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "",
            "/outside.md",
            "../outside.md",
            "folder/../../outside.md",
            r"..\outside.md",
            "C:/outside.md",
        ],
    )
    async def test_rejects_paths_outside_the_vault(self, fake_cli, path):
        executable, calls = fake_cli
        client = ObsidianCLIClient(cli_path=executable)

        with pytest.raises(ValueError):
            await client.get_note(path)

        assert not calls.exists()

    @pytest.mark.asyncio
    async def test_note_exists_only_swallows_missing_note_failures(self, fake_cli, monkeypatch):
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_EXIT", "1")
        monkeypatch.setenv(
            "FAKE_OBSIDIAN_STDERR",
            "Error: ENOENT: no such file or directory, open '/vault/Missing.md'",
        )
        client = ObsidianCLIClient(cli_path=executable)

        with pytest.raises(NoteNotFoundError) as exc_info:
            await client.get_note("Missing.md")
        assert exc_info.value.path == "Missing.md"

        assert await client.note_exists("Missing.md") is False

    @pytest.mark.asyncio
    async def test_note_exists_propagates_unrelated_cli_failures(self, fake_cli, monkeypatch):
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_EXIT", "1")
        monkeypatch.setenv("FAKE_OBSIDIAN_STDERR", "Error: vault is locked")
        client = ObsidianCLIClient(cli_path=executable)

        with pytest.raises(ObsidianCLIError) as exc_info:
            await client.note_exists("Note.md")

        assert type(exc_info.value) is ObsidianCLIError

    @pytest.mark.asyncio
    async def test_create_enoent_is_not_misclassified_as_a_missing_note(
        self, fake_cli, monkeypatch
    ):
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_EXIT", "1")
        monkeypatch.setenv(
            "FAKE_OBSIDIAN_STDERR",
            "Error: ENOENT: no such file or directory, open '/vault/Missing/Note.md'",
        )
        client = ObsidianCLIClient(cli_path=executable)

        with pytest.raises(ObsidianCLIError) as exc_info:
            await client.create_note("Missing/Note.md", "body")

        assert type(exc_info.value) is ObsidianCLIError


# ---------------------------------------------------------------------------
# Protocol Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Test that ObsidianCLIClient satisfies VaultClient Protocol."""

    def test_isinstance_check(self):
        """ObsidianCLIClient should pass isinstance check for VaultClient."""
        client = ObsidianCLIClient(cli_path="/usr/bin/obsidian")
        assert isinstance(client, VaultClient)
