"""
Obsidian CLI Client for Obsidian Brain MCP.

Implements the VaultClient Protocol using asyncio.create_subprocess_exec
to call the Obsidian CLI binary. All subprocess calls use list-form args
(never shell=True) and have explicit timeouts.

The CLI binary is located via shutil.which with OBSIDIAN_CLI_PATH env var override.
"""

import asyncio
import os
import re
import shutil
import time
from pathlib import PurePosixPath
from typing import Any

from .exceptions import (
    CLINotFoundError,
    CLITimeoutError,
    NoteNotFoundError,
    ObsidianCLIError,
    ObsidianNotRunningError,
)
from .parsers import (
    parse_daily,
    parse_note_read,
    parse_search_results,
)

# Match only the known startup message, not arbitrary timestamped note content.
_OBSIDIAN_LOG_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} Load(?:ed|ing) (?:main|updated) app package(?: .*)?$"
)
_OBSIDIAN_RUNNING_TTL = 5.0
_clock = time.monotonic
_obsidian_running_until = 0.0

# The real Obsidian CLI always exits 0 and reports failures as a single
# line of stdout instead of via returncode/stderr, so these classify it.
_NOTE_NOT_FOUND_RE = re.compile(r'^Error: File "(?P<path>.+)" not found\.$')
_VAULT_NOT_FOUND_RE = re.compile(r"^Vault not found\.$")
_GENERIC_ERROR_RE = re.compile(r"^Error: .+$")
_CREATE_RESULT_RE = re.compile(r"^(?:Created|Overwrote): (?P<path>.+)$", re.MULTILINE)
# Commands whose successful stdout IS arbitrary note content, so a generic
# "Error: …" line there may be the note itself rather than a failure.
_CONTENT_COMMANDS = frozenset({"read", "daily:read"})


def _classify_stdout_error(
    output: str, args: tuple[str, ...], command: list[str]
) -> ObsidianCLIError | None:
    """Classify a whole-output stdout error line from a successful (exit 0) run.

    Matching is against the ENTIRE trimmed output, never a substring: a
    note's own content may legitimately contain text that looks like one
    of these messages, and only a whole-line match can tell that apart
    from a real CLI-reported failure.
    """
    stripped = output.strip()

    not_found = _NOTE_NOT_FOUND_RE.match(stripped)
    if not_found:
        target = next((arg.removeprefix("path=") for arg in args if arg.startswith("path=")), None)
        if not_found.group("path") == target:
            return NoteNotFoundError(not_found.group("path"), command=command)

    if _VAULT_NOT_FOUND_RE.match(stripped):
        return ObsidianCLIError(returncode=0, stderr=stripped, command=command)

    # A read's whole output can be a one-line note that merely starts with
    # "Error: ", so the catch-all only applies where stdout is a status line.
    if args and args[0] not in _CONTENT_COMMANDS and _GENERIC_ERROR_RE.match(stripped):
        return ObsidianCLIError(returncode=0, stderr=stripped, command=command)

    return None


def find_cli_binary() -> str:
    """Locate the Obsidian CLI binary.

    Checks OBSIDIAN_CLI_PATH env var first, then falls back to shutil.which.

    Returns:
        Absolute path to the obsidian CLI binary.

    Raises:
        CLINotFoundError: If the binary cannot be found.
    """
    # Check env var override first
    env_path = os.environ.get("OBSIDIAN_CLI_PATH")
    if env_path:
        if os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            return env_path
        raise CLINotFoundError(searched_paths=f"OBSIDIAN_CLI_PATH={env_path}")

    # Fall back to PATH lookup
    found = shutil.which("obsidian")
    if found:
        return found

    raise CLINotFoundError(searched_paths="PATH")


def _validate_path(path: str, *, allow_root: bool = False) -> None:
    """Require a vault-relative path that cannot escape the vault root."""
    if "\x00" in path:
        raise ValueError(f"Path contains null bytes: {path!r}")
    if allow_root and path in {"", "/"}:
        return

    parsed = PurePosixPath(path)
    if (
        not path
        or parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or "\\" in path
        or re.match(r"^[A-Za-z]:", path)
    ):
        raise ValueError(f"Path must stay within the vault root: {path!r}")


async def _check_obsidian_running() -> None:
    """Verify that the Obsidian desktop app is running.

    The Obsidian 1.12+ CLI communicates with a running instance via IPC.
    Without a running instance, CLI commands launch a new Electron process
    that hangs indefinitely waiting for GUI interaction.

    Raises:
        ObsidianNotRunningError: If no Obsidian process is detected.
    """
    global _obsidian_running_until

    if _clock() < _obsidian_running_until:
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            "pgrep",
            "-f",
            "obsidian.*app.asar",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode != 0 or not stdout.strip():
            raise ObsidianNotRunningError()
        _obsidian_running_until = _clock() + _OBSIDIAN_RUNNING_TTL
    except FileNotFoundError:
        # pgrep not available -- skip check rather than block
        pass
    except asyncio.TimeoutError:
        # pgrep itself hung -- skip check rather than block
        pass


def _filter_log_lines(output: str) -> str:
    """Remove known Obsidian startup lines without consuming note content."""
    lines = output.splitlines(keepends=True)
    first_content = 0
    while first_content < len(lines):
        line = lines[first_content].rstrip("\r\n")
        if not _OBSIDIAN_LOG_RE.fullmatch(line):
            break
        first_content += 1
    return "".join(lines[first_content:])


class ObsidianCLIClient:
    """Vault client that executes operations via Obsidian CLI subprocess calls.

    Implements the VaultClient Protocol. All CLI calls use
    asyncio.create_subprocess_exec with list-form arguments (never shell=True)
    and have explicit timeouts via asyncio.wait_for.

    Args:
        cli_path: Optional binary path. Discovery is deferred until the first command.
        vault: Optional vault name. Defaults to OBSIDIAN_VAULT when unset.
        timeout: Default timeout in seconds for CLI commands.
    """

    def __init__(
        self,
        cli_path: str | None = None,
        vault: str | None = None,
        timeout: float = 30.0,
    ):
        self.cli_path = cli_path
        self.vault = vault if vault is not None else os.environ.get("OBSIDIAN_VAULT")
        self.timeout = timeout

    async def _run(self, *args: str, timeout: float | None = None) -> str:
        """Execute a CLI command and return stdout.

        Args:
            *args: CLI command arguments (e.g., "read", 'path="test.md"').
            timeout: Override default timeout in seconds.

        Returns:
            Decoded stdout string.

        Raises:
            ObsidianCLIError: On non-zero exit, non-empty stderr, or a
                recognized stdout error line -- the real CLI always exits 0
                and reports failures as a line of stdout.
            NoteNotFoundError: When stdout reports the targeted note missing.
        """
        cli_path = self.cli_path
        if cli_path is None:
            cli_path = find_cli_binary()
            self.cli_path = cli_path

        # Without a running app, CLI commands launch Electron and hang.
        await _check_obsidian_running()

        cmd = [cli_path]
        if self.vault:
            cmd.append(f"vault={self.vault}")
        cmd.extend(args)

        effective_timeout = timeout if timeout is not None else self.timeout

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise CLINotFoundError(searched_paths=f"cli_path={cli_path}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise CLITimeoutError(timeout=effective_timeout, command=cmd)

        stderr_text = stderr.decode().strip()
        if proc.returncode != 0 or stderr_text:
            raise ObsidianCLIError(
                returncode=proc.returncode,
                stderr=stderr_text,
                command=cmd,
            )

        cleaned = _filter_log_lines(stdout.decode())
        error = _classify_stdout_error(cleaned, args, cmd)
        if error is not None:
            raise error
        return cleaned

    # -------------------------------------------------------------------------
    # Directory Operations
    # -------------------------------------------------------------------------
    async def _get_file_lines(self, path: str) -> list[str]:
        _validate_path(path, allow_root=True)
        args = ["files"]
        if path and path != "/":
            args.append(f"folder={path}")
        output = await self._run(*args)
        return [line.strip() for line in output.strip().splitlines() if line.strip()]

    async def list_directory(self, path: str = "/") -> list[dict[str, Any]]:
        """List every file recursively under the specified path.

        Note: The Obsidian CLI ``files`` command returns plain text
        (one vault-relative file path per line), not JSON, and it
        recurses through subfolders. It never lists folders or emits a
        trailing slash, so every entry is a file; the ``name``/``type``
        dict shape is kept for callers, with ``type`` always ``"file"``.
        """
        lines = await self._get_file_lines(path)
        return [{"name": entry, "type": "file"} for entry in lines]

    async def get_all_files(self, path: str = "/") -> list[str]:
        """Get every file path under a directory, regardless of extension.

        Omitting ``ext`` is intentional: the Obsidian CLI ``files`` command
        then lists Markdown notes and every attachment type. Its output is
        plain text with one path per line, so this uses ``_run`` directly.
        """
        return await self._get_file_lines(path)

    # -------------------------------------------------------------------------
    # Note Operations
    # -------------------------------------------------------------------------

    async def get_note(self, path: str) -> dict[str, Any]:
        """Get a note's content and metadata.

        Note: The Obsidian CLI ``read`` command returns raw markdown text,
        not JSON (the ``format=json`` flag is ignored).  We use ``_run``
        and pass the raw text to ``parse_note_read`` which extracts
        frontmatter and content.
        """
        _validate_path(path)
        output = await self._run("read", f"path={path}")
        return parse_note_read(output, path=path)

    async def note_exists(self, path: str) -> bool:
        """Check if a note exists in the vault."""
        _validate_path(path)
        try:
            await self.get_note(path)
            return True
        except NoteNotFoundError:
            return False

    async def create_note(self, path: str, content: str) -> str:
        """Create a new note at an exact vault-relative path.

        Returns the vault-relative path Obsidian actually created,
        parsed from its ``Created: <path>``/``Overwrote: <path>`` stdout
        line (falling back to the requested ``path`` if that line is
        absent). Obsidian dedupes an existing target instead of failing
        or overwriting it -- creating "Note.md" a second time creates
        "Note 1.md" and leaves the original file untouched.
        """
        _validate_path(path)
        output = await self._run("create", f"path={path}", f"content={content}")
        match = _CREATE_RESULT_RE.search(output)
        return match.group("path").strip() if match else path

    async def update_note(self, path: str, content: str) -> None:
        """Replace a note's entire content."""
        _validate_path(path)
        await self._run("create", f"path={path}", f"content={content}", "overwrite")

    async def append_to_note(self, path: str, content: str) -> None:
        """Append content to an existing note."""
        _validate_path(path)
        await self._run("append", f"path={path}", f"content={content}")

    async def delete_note(self, path: str) -> None:
        """Delete a note from the vault."""
        _validate_path(path)
        await self._run("delete", f"path={path}")

    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------

    async def search_simple(self, query: str) -> list[dict[str, Any]]:
        """Search the vault and return each matching file with its matching lines."""
        output = await self._run("search:context", f"query={query}", "format=text")
        return parse_search_results(output)

    # -------------------------------------------------------------------------
    # Daily Notes
    # -------------------------------------------------------------------------

    async def get_daily_path(self, date: str | None = None) -> str:
        """Resolve the daily note's vault-relative path, created or not."""
        args = ["daily:path"]
        if date:
            args.append(f"date={date}")
        return (await self._run(*args)).strip()

    async def get_daily_note(self, date: str | None = None) -> dict[str, Any]:
        """Get today's daily note (or a specific date's).

        Note: The Obsidian CLI ``daily:read`` command returns raw markdown
        text, not JSON.  We use ``_run`` and pass the raw text to
        ``parse_daily``.
        """
        args = ["daily:read"]
        if date:
            args.append(f"date={date}")
        output = await self._run(*args)
        return parse_daily(output)

    async def append_daily(self, content: str, date: str | None = None) -> None:
        """Append content to today's daily note."""
        args = ["daily:append", f"content={content}"]
        if date:
            args.append(f"date={date}")
        await self._run(*args)
