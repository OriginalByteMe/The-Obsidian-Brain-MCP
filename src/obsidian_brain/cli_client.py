"""
Obsidian CLI Client for Obsidian Brain MCP.

Implements the VaultClient Protocol using asyncio.create_subprocess_exec
to call the Obsidian CLI binary. All subprocess calls use list-form args
(never shell=True) and have explicit timeouts.

The CLI binary is located via shutil.which with OBSIDIAN_CLI_PATH env var override.
"""

import asyncio
import json
import os
import re
import shutil
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
    parse_file_list,
    parse_note_read,
    parse_search_results,
    parse_tags,
)

# Pattern matching Obsidian Electron startup log lines that leak into stdout.
# Example: "2026-03-08 12:02:59 Loaded updated app package ..."
_OBSIDIAN_LOG_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ")


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


def _validate_path(path: str) -> None:
    """Validate a note path for safety.

    Args:
        path: Note path to validate.

    Raises:
        ValueError: If path contains null bytes or other dangerous characters.
    """
    if "\x00" in path:
        raise ValueError(f"Path contains null bytes: {path!r}")


def _split_note_path(path: str) -> tuple[str, str]:
    """Split a full note path into folder and name components.

    The CLI uses separate name= and path= args for create/update.
    Example: "Projects/Active/note.md" -> ("Projects/Active", "note.md")

    Args:
        path: Full note path (e.g., "folder/note.md").

    Returns:
        Tuple of (folder, name). Folder is empty string if no folder.
    """
    p = PurePosixPath(path)
    folder = str(p.parent) if str(p.parent) != "." else ""
    name = p.name
    return folder, name


async def _check_obsidian_running() -> None:
    """Verify that the Obsidian desktop app is running.

    The Obsidian 1.12+ CLI communicates with a running instance via IPC.
    Without a running instance, CLI commands launch a new Electron process
    that hangs indefinitely waiting for GUI interaction.

    Raises:
        ObsidianNotRunningError: If no Obsidian process is detected.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "pgrep", "-f", "obsidian.*app.asar",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode != 0 or not stdout.strip():
            raise ObsidianNotRunningError()
    except FileNotFoundError:
        # pgrep not available -- skip check rather than block
        pass
    except asyncio.TimeoutError:
        # pgrep itself hung -- skip check rather than block
        pass


def _filter_log_lines(output: str) -> str:
    """Remove Obsidian Electron startup log lines from CLI stdout.

    The Obsidian binary sometimes emits timestamped log lines to stdout
    (e.g., "2026-03-08 12:02:59 Loaded updated app package ...") before
    the actual command output. These must be stripped to avoid corrupting
    JSON parsing or plain-text parsing.

    Args:
        output: Raw stdout string from the CLI process.

    Returns:
        Cleaned output with log lines removed.
    """
    lines = output.split("\n")
    filtered = [line for line in lines if not _OBSIDIAN_LOG_RE.match(line)]
    return "\n".join(filtered)


class ObsidianCLIClient:
    """Vault client that executes operations via Obsidian CLI subprocess calls.

    Implements the VaultClient Protocol. All CLI calls use
    asyncio.create_subprocess_exec with list-form arguments (never shell=True)
    and have explicit timeouts via asyncio.wait_for.

    Args:
        cli_path: Path to the obsidian binary. If None, uses find_cli_binary().
        vault: Optional vault name for multi-vault setups.
        timeout: Default timeout in seconds for CLI commands.
    """

    def __init__(
        self,
        cli_path: str | None = None,
        vault: str | None = None,
        timeout: float = 30.0,
    ):
        if cli_path is not None:
            self.cli_path = cli_path
        else:
            self.cli_path = find_cli_binary()
        self.vault = vault
        self.timeout = timeout

    async def _run(self, *args: str, timeout: float | None = None) -> str:
        """Execute a CLI command and return stdout.

        Args:
            *args: CLI command arguments (e.g., "read", 'path="test.md"').
            timeout: Override default timeout in seconds.

        Returns:
            Decoded stdout string.

        Raises:
            ObsidianCLIError: On non-zero exit code.
            CLITimeoutError: If command exceeds timeout.
        """
        # Pre-flight: ensure Obsidian desktop app is running.
        # Without this, CLI commands hang for the full timeout duration
        # because the Electron binary launches a GUI instance instead of
        # processing the command via IPC.
        await _check_obsidian_running()

        cmd = [self.cli_path, *args]
        if self.vault:
            cmd.append(f"vault={self.vault}")

        effective_timeout = timeout if timeout is not None else self.timeout

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise CLITimeoutError(timeout=effective_timeout, command=cmd)

        if proc.returncode != 0:
            raise ObsidianCLIError(
                returncode=proc.returncode,
                stderr=stderr.decode().strip(),
                command=cmd,
            )

        return _filter_log_lines(stdout.decode())

    async def _run_json(self, *args: str, timeout: float | None = None) -> Any:
        """Execute a CLI command and parse JSON output.

        Appends format=json to the args and parses the result.

        Args:
            *args: CLI command arguments.
            timeout: Override default timeout.

        Returns:
            Parsed JSON data.
        """
        output = await self._run(*args, "format=json", timeout=timeout)
        return json.loads(output)

    # -------------------------------------------------------------------------
    # Directory Operations
    # -------------------------------------------------------------------------

    async def list_directory(self, path: str = "/") -> list[dict[str, Any]]:
        """List files and folders at the specified path.

        Note: The Obsidian CLI ``files`` command returns plain text
        (one entry per line), not JSON.  We use ``_run`` and parse
        the text output directly.
        """
        _validate_path(path)
        args = ["files"]
        if path and path != "/":
            args.append(f"folder={path}")
        output = await self._run(*args)
        result = []
        for line in output.strip().splitlines():
            entry = line.strip()
            if not entry:
                continue
            is_folder = entry.endswith("/")
            result.append({
                "name": entry.rstrip("/"),
                "type": "folder" if is_folder else "file",
            })
        return result

    async def get_all_files(self, path: str = "/") -> list[str]:
        """Get all file paths under a directory.

        Note: The Obsidian CLI ``files`` command returns plain text
        (one path per line), not JSON, even when ``format=json`` is
        specified.  We therefore use ``_run`` instead of ``_run_json``.
        """
        _validate_path(path)
        args = ["files", "ext=md"]
        if path and path != "/":
            args.append(f"folder={path}")
        output = await self._run(*args)
        # Plain-text output: one file path per line
        return [line.strip() for line in output.strip().splitlines() if line.strip()]

    # -------------------------------------------------------------------------
    # Note Operations
    # -------------------------------------------------------------------------

    async def get_note(self, path: str, include_metadata: bool = True) -> dict[str, Any]:
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
            await self.get_note(path, include_metadata=False)
            return True
        except ObsidianCLIError:
            return False

    async def create_note(self, path: str, content: str) -> None:
        """Create a new note."""
        _validate_path(path)
        folder, name = _split_note_path(path)
        args = ["create", f"name={name}"]
        if folder:
            args.append(f"path={folder}")
        args.extend([f"content={content}", "--silent"])
        await self._run(*args)

    async def update_note(self, path: str, content: str) -> None:
        """Replace a note's entire content."""
        _validate_path(path)
        folder, name = _split_note_path(path)
        args = ["create", f"name={name}"]
        if folder:
            args.append(f"path={folder}")
        args.extend([f"content={content}", "--overwrite", "--silent"])
        await self._run(*args)

    async def append_to_note(self, path: str, content: str) -> None:
        """Append content to an existing note."""
        _validate_path(path)
        _folder, name = _split_note_path(path)
        await self._run("append", f"file={name}", f"content={content}")

    async def delete_note(self, path: str) -> None:
        """Delete a note from the vault."""
        _validate_path(path)
        _folder, name = _split_note_path(path)
        await self._run("delete", f"file={name}")

    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------

    async def search_simple(
        self, query: str, context_length: int = 100
    ) -> list[dict[str, Any]]:
        """Perform text search across the vault."""
        data = await self._run_json("search", f"query={query}")
        return parse_search_results(data)

    # -------------------------------------------------------------------------
    # Daily Notes
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Tags and Links
    # -------------------------------------------------------------------------

    async def get_tags(self) -> dict[str, int]:
        """Get all tags in the vault with their counts."""
        data = await self._run_json("tags")
        return parse_tags(data)

    async def get_backlinks(self, path: str) -> list[str]:
        """Get notes that link to the specified note."""
        _validate_path(path)
        _folder, name = _split_note_path(path)
        data = await self._run_json("backlinks", f"file={name}")
        if isinstance(data, list):
            return [item if isinstance(item, str) else item.get("path", "") for item in data]
        return []

    async def get_links(self, path: str) -> list[str]:
        """Get outgoing links from the specified note."""
        _validate_path(path)
        _folder, name = _split_note_path(path)
        data = await self._run_json("links", f"file={name}")
        if isinstance(data, list):
            return [item if isinstance(item, str) else item.get("path", "") for item in data]
        return []
