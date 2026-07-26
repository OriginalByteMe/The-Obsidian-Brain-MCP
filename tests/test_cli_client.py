"""Tests for ObsidianCLIClient with mocked subprocess."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from obsidian_brain.cli_client import (
    ObsidianCLIClient,
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
# Registered-CLI failure modes (empirically observed against Obsidian 1.12.7)
# ---------------------------------------------------------------------------


class TestRegisteredCliFailureModes:
    """Pin the four failure shapes proven against the real registered CLI."""

    @pytest.fixture
    def client(self):
        return ObsidianCLIClient(cli_path="/usr/bin/obsidian")

    @pytest.mark.asyncio
    async def test_cli_disabled_sentinel_raises_for_data_command(self, client):
        """The disabled sentinel must not leak through as note content."""
        proc = _make_mock_process(
            stdout=(
                "Command line interface is not enabled. "
                "Please turn it on in Settings > General > Advanced."
            )
        )
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(ObsidianCLIError) as exc_info:
                await client._run("read", "path=Note.md")
        assert exc_info.value.stderr == (
            "Obsidian's command line interface is disabled. Enable it in Obsidian: "
            'Settings > General > Advanced > "Command line interface".'
        )

    @pytest.mark.asyncio
    async def test_cli_disabled_sentinel_raises_for_non_data_command(self, client):
        """Applies unconditionally, not just to data commands."""
        proc = _make_mock_process(
            stdout=(
                "Command line interface is not enabled. "
                "Please turn it on in Settings > General > Advanced."
            )
        )
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(ObsidianCLIError) as exc_info:
                await client._run("create", "path=Note.md", "content=x")
        assert "Settings > General > Advanced" in exc_info.value.stderr
        assert "enable" in exc_info.value.stderr.lower()

    @pytest.mark.asyncio
    async def test_vault_not_found_raises_actionable_error_for_data_command(self, client):
        proc = _make_mock_process(stdout="Vault not found.")
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(ObsidianCLIError) as exc_info:
                await client._run("read", "path=Note.md")
        assert exc_info.value.stderr == (
            "Vault not found. Set OBSIDIAN_VAULT to a vault name or id from "
            "~/.config/obsidian/obsidian.json, or open the target vault in Obsidian."
        )

    @pytest.mark.asyncio
    async def test_command_not_found_did_you_mean_variant_raises_for_invoked_command(self, client):
        proc = _make_mock_process(
            stdout='Error: Command "files" not found. Did you mean: links, bases?'
        )
        with (
            patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc),
            patch("obsidian_brain.cli_client.asyncio.sleep"),
        ):
            with pytest.raises(ObsidianCLIError) as exc_info:
                await client._run("files")
        assert (
            exc_info.value.stderr == 'Error: Command "files" not found. Did you mean: links, bases?'
        )

    @pytest.mark.asyncio
    async def test_command_not_found_plugin_variant_raises_for_invoked_command(self, client):
        proc = _make_mock_process(
            stdout='Error: Command "bogus:cmd" not found. It may require a plugin to be enabled.'
        )
        with (
            patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc),
            patch("obsidian_brain.cli_client.asyncio.sleep"),
        ):
            with pytest.raises(ObsidianCLIError) as exc_info:
                await client._run("bogus:cmd")
        assert (
            exc_info.value.stderr
            == 'Error: Command "bogus:cmd" not found. It may require a plugin to be enabled.'
        )

    @pytest.mark.asyncio
    async def test_command_not_found_for_a_different_command_is_data_not_a_failure(self, client):
        """The whole point of the command-equality check: a note body that merely
        LOOKS like a command-not-found error for some OTHER command must come
        back as data, not get misclassified as a CLI failure."""
        body = 'Error: Command "something-else" not found. It may require a plugin to be enabled.'
        proc = _make_mock_process(stdout=body)
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            result = await client._run("read", "path=Note.md")
        assert result == body

    @pytest.mark.asyncio
    async def test_multiline_generic_error_raises_for_non_data_command(self, client):
        stdout = (
            "Error: Missing required parameter: query=<text>\n"
            "Usage: search query=<text> [path=<folder>] [format=json|text]"
        )
        proc = _make_mock_process(stdout=stdout)
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(ObsidianCLIError) as exc_info:
                await client._run("create", "path=Note.md")
        assert exc_info.value.stderr == stdout

    @pytest.mark.asyncio
    async def test_multiline_generic_error_is_exempt_for_data_command(self, client):
        """Data commands stay exempt from the generic rule even multi-line."""
        stdout = (
            "Error: Missing required parameter: query=<text>\n"
            "Usage: search query=<text> [path=<folder>] [format=json|text]"
        )
        proc = _make_mock_process(stdout=stdout)
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            result = await client._run("search", "query=")
        assert result == stdout

    @pytest.mark.asyncio
    async def test_cli_not_running_stderr_raises_obsidian_not_running(self, client):
        proc = _make_mock_process(
            stderr=(
                "The CLI is unable to find Obsidian. "
                "Please make sure Obsidian is running and try again."
            ),
            returncode=1,
        )
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            with pytest.raises(ObsidianNotRunningError):
                await client._run("version")
        assert mock_exec.call_count == 1

    @pytest.mark.asyncio
    async def test_cold_vault_open_race_retries_once_and_succeeds(self, client):
        """First call loses the async-handler-registration race; the retry succeeds."""
        losing = _make_mock_process(
            stdout='Error: Command "files" not found. Did you mean: links, bases?'
        )
        winning = _make_mock_process(stdout="Note.md\nOther.md")
        with (
            patch(
                "obsidian_brain.cli_client.asyncio.create_subprocess_exec",
                side_effect=[losing, winning],
            ) as mock_exec,
            patch("obsidian_brain.cli_client.asyncio.sleep") as mock_sleep,
        ):
            result = await client._run("files")

        assert result == "Note.md\nOther.md"
        assert mock_exec.call_count == 2
        mock_sleep.assert_awaited_once_with(0.75)

    @pytest.mark.asyncio
    async def test_cold_vault_open_race_gives_up_after_one_retry(self, client):
        """Bounded to a single retry -- two losses in a row still raise."""
        losing = _make_mock_process(
            stdout='Error: Command "files" not found. Did you mean: links, bases?'
        )
        with (
            patch(
                "obsidian_brain.cli_client.asyncio.create_subprocess_exec",
                side_effect=[losing, losing],
            ) as mock_exec,
            patch("obsidian_brain.cli_client.asyncio.sleep"),
        ):
            with pytest.raises(ObsidianCLIError):
                await client._run("files")

        assert mock_exec.call_count == 2


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
        """Should return False when the CLI reports the note missing on stdout."""
        proc = _make_mock_process(stdout='Error: File "missing.md" not found.')
        with patch("obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc):
            assert await client.note_exists("missing.md") is False

    @pytest.mark.asyncio
    async def test_create_note(self, client):
        """Should target the exact vault-relative path and return the parsed created path."""
        proc = _make_mock_process(stdout="Created: folder/note 1.md\n")
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            result = await client.create_note("folder/note.md", "# Content")
            assert result == "folder/note 1.md"
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
        """Should call obsidian files with folder arg and return recursive file paths."""
        # The CLI files command recurses through subfolders and returns
        # vault-relative file paths only -- it never lists folders.
        plain_output = "note.md\nsubfolder/nested.md\n"
        proc = _make_mock_process(stdout=plain_output)
        with patch(
            "obsidian_brain.cli_client.asyncio.create_subprocess_exec", return_value=proc
        ) as mock_exec:
            result = await client.list_directory("Projects")
            assert len(result) == 2
            assert result[0] == {"name": "note.md", "type": "file"}
            assert result[1] == {"name": "subfolder/nested.md", "type": "file"}
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
                "Created: Projects/Nested/Note.md\n",
                ["create", "path=Projects/Nested/Note.md", "content=body"],
            ),
            (
                "update_note",
                ("Projects/Nested/Note.md", "body"),
                "Overwrote: Projects/Nested/Note.md\n",
                ["create", "path=Projects/Nested/Note.md", "content=body", "overwrite"],
            ),
            (
                "append_to_note",
                ("Projects/Nested/Note.md", "body"),
                "Appended to: Projects/Nested/Note.md\n",
                ["append", "path=Projects/Nested/Note.md", "content=body"],
            ),
            (
                "delete_note",
                ("Projects/Nested/Note.md",),
                "Moved to trash: Projects/Nested/Note.md\n",
                ["delete", "path=Projects/Nested/Note.md"],
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
    async def test_read_filters_loaded_main_app_package_log_line(self, fake_cli, monkeypatch):
        """The real CLI's startup line reads "Loaded main app package", not "updated"."""
        executable, _calls = fake_cli
        monkeypatch.setenv(
            "FAKE_OBSIDIAN_STDOUT",
            "2026-07-26 09:00:00 Loaded main app package /tmp/app.asar\n# Real content\n",
        )
        client = ObsidianCLIClient(cli_path=executable)

        note = await client.get_note("Note.md")

        assert note["content"] == "# Real content\n"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "",
            "/outside.md",
            "../outside.md",
            "folder/../../outside.md",
            "folder//note.md",
            "folder/./note.md",
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
    @pytest.mark.parametrize(
        ("method", "arguments"),
        [
            ("get_note", ("Missing.md",)),
            ("append_to_note", ("Missing.md", "new text")),
            ("delete_note", ("Missing.md",)),
        ],
    )
    async def test_missing_note_stdout_message_raises_note_not_found(
        self, fake_cli, monkeypatch, method, arguments
    ):
        """The real CLI reports a missing note on stdout with exit 0, never stderr/ENOENT."""
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", 'Error: File "Missing.md" not found.\n')
        client = ObsidianCLIClient(cli_path=executable)

        with pytest.raises(NoteNotFoundError) as exc_info:
            await getattr(client, method)(*arguments)
        assert exc_info.value.path == "Missing.md"

    @pytest.mark.asyncio
    async def test_note_exists_only_swallows_missing_note_failures(self, fake_cli, monkeypatch):
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", 'Error: File "Missing.md" not found.\n')
        client = ObsidianCLIClient(cli_path=executable)

        with pytest.raises(NoteNotFoundError) as exc_info:
            await client.get_note("Missing.md")
        assert exc_info.value.path == "Missing.md"

        assert await client.note_exists("Missing.md") is False

    @pytest.mark.asyncio
    async def test_vault_not_found_stdout_is_not_misclassified_as_a_missing_note(
        self, fake_cli, monkeypatch
    ):
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", "Vault not found.\n")
        client = ObsidianCLIClient(cli_path=executable, vault="Work")

        with pytest.raises(ObsidianCLIError) as exc_info:
            await client.get_note("Note.md")
        assert type(exc_info.value) is ObsidianCLIError
        assert "Work" in str(exc_info.value)

        with pytest.raises(ObsidianCLIError) as exc_info:
            await client.note_exists("Note.md")
        assert type(exc_info.value) is ObsidianCLIError

    @pytest.mark.asyncio
    async def test_unknown_command_stdout_message_raises_cli_error(self, fake_cli, monkeypatch):
        """A genuinely unknown command still fails, after the one bounded retry."""
        executable, _calls = fake_cli
        monkeypatch.setenv(
            "FAKE_OBSIDIAN_STDOUT",
            'Error: Command "bogus:cmd" not found. It may require a plugin to be enabled.\n',
        )
        monkeypatch.setattr("obsidian_brain.cli_client.asyncio.sleep", AsyncMock())
        client = ObsidianCLIClient(cli_path=executable)

        with pytest.raises(ObsidianCLIError) as exc_info:
            await client._run("bogus:cmd")
        assert type(exc_info.value) is ObsidianCLIError

    @pytest.mark.asyncio
    async def test_note_content_merely_containing_error_text_is_read_normally(
        self, fake_cli, monkeypatch
    ):
        """A note whose raw content merely mentions the error phrase must not be misclassified."""
        executable, _calls = fake_cli
        monkeypatch.setenv(
            "FAKE_OBSIDIAN_STDOUT",
            "# Log\n"
            'Yesterday I saw: Error: File "missing.md" not found.\n'
            "That was resolved by re-syncing.\n",
        )
        client = ObsidianCLIClient(cli_path=executable)

        note = await client.get_note("Log.md")

        assert 'Error: File "missing.md" not found.' in note["content"]

    @pytest.mark.asyncio
    async def test_one_line_note_starting_with_error_is_content_not_a_failure(
        self, fake_cli, monkeypatch
    ):
        """A note whose ENTIRE body is an `Error: …` line is still a note."""
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", "Error: retry later\n")
        client = ObsidianCLIClient(cli_path=executable)

        note = await client.get_note("Snippets/Retry.md")

        assert note["content"].strip() == "Error: retry later"

    @pytest.mark.asyncio
    async def test_single_listing_or_search_line_starting_with_error_is_data(
        self, fake_cli, monkeypatch
    ):
        """`files` and `search:context` output is user data, not a status line."""
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", "Error: retry later.md\n")
        client = ObsidianCLIClient(cli_path=executable)

        assert await client.get_all_files() == ["Error: retry later.md"]

        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", "Error: retry later.md:3: hit\n")
        assert await client.search_simple("hit") == [
            {"path": "Error: retry later.md", "matches": ["hit"], "score": 0.0}
        ]

    @pytest.mark.asyncio
    async def test_search_no_matches_found_yields_empty_list(self, fake_cli, monkeypatch):
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", "No matches found.\n")
        client = ObsidianCLIClient(cli_path=executable)

        result = await client.search_simple("nothing")

        assert result == []

    @pytest.mark.asyncio
    async def test_create_note_returns_created_path(self, fake_cli, monkeypatch):
        """The parsed Created: path is returned, distinct from the requested path."""
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", "Created: Actual/Note.md\n")
        client = ObsidianCLIClient(cli_path=executable)

        result = await client.create_note("Note.md", "body")

        assert result == "Actual/Note.md"

    @pytest.mark.asyncio
    async def test_create_note_dedupe_returns_the_actual_created_path(self, fake_cli, monkeypatch):
        """Obsidian dedupes an existing target instead of failing or overwriting it."""
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", "Created: Note 1.md\n")
        client = ObsidianCLIClient(cli_path=executable)

        result = await client.create_note("Note.md", "body")

        assert result == "Note 1.md"

    @pytest.mark.asyncio
    async def test_create_note_parses_overwrote_line_too(self, fake_cli, monkeypatch):
        """create_note's parser recognizes Overwrote: as well as Created:."""
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", "Overwrote: Actual/Note.md\n")
        client = ObsidianCLIClient(cli_path=executable)

        result = await client.create_note("Note.md", "body")

        assert result == "Actual/Note.md"

    @pytest.mark.asyncio
    async def test_create_note_falls_back_to_requested_path_without_a_created_line(
        self, fake_cli, monkeypatch
    ):
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDOUT", "")
        client = ObsidianCLIClient(cli_path=executable)

        result = await client.create_note("Note.md", "body")

        assert result == "Note.md"

    @pytest.mark.asyncio
    async def test_stderr_text_raises_even_with_exit_zero(self, fake_cli, monkeypatch):
        """Belt-and-braces: non-empty stderr still raises even at exit 0, for
        CLI builds other than the real one (which never writes to stderr)."""
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_STDERR", "unexpected warning")
        client = ObsidianCLIClient(cli_path=executable)

        with pytest.raises(ObsidianCLIError) as exc_info:
            await client.get_note("Note.md")
        assert exc_info.value.returncode == 0

    @pytest.mark.asyncio
    async def test_non_zero_exit_still_raises_cli_error(self, fake_cli, monkeypatch):
        executable, _calls = fake_cli
        monkeypatch.setenv("FAKE_OBSIDIAN_EXIT", "1")
        monkeypatch.setenv("FAKE_OBSIDIAN_STDERR", "boom")
        client = ObsidianCLIClient(cli_path=executable)

        with pytest.raises(ObsidianCLIError) as exc_info:
            await client.get_note("Note.md")
        assert exc_info.value.returncode == 1


# ---------------------------------------------------------------------------
# Protocol Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Test that ObsidianCLIClient satisfies VaultClient Protocol."""

    def test_isinstance_check(self):
        """ObsidianCLIClient should pass isinstance check for VaultClient."""
        client = ObsidianCLIClient(cli_path="/usr/bin/obsidian")
        assert isinstance(client, VaultClient)
