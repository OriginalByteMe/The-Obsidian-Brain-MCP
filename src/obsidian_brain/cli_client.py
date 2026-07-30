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
from pathlib import Path, PurePosixPath
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

# Startup output is produced by the Electron application launcher, not by the
# registered CLI. Treat it as a wrong-binary failure before any command parser
# can mistake it for note content, file paths, or search results.
_OBSIDIAN_APP_PREAMBLE_RE = re.compile(
    r"^(?:"
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} "
    r"Load(?:ed|ing) (?:main|updated) app package"
    r"|Your Obsidian installer is out of date\."
    r"|Ignored: Error:)"
)

_OBSIDIAN_APP_PREAMBLE_MESSAGE = (
    "The configured Obsidian executable emitted desktop application startup output "
    "instead of CLI data. Install and register obsidian-cli, or set OBSIDIAN_CLI_PATH "
    "to the real CLI binary."
)

# The real Obsidian CLI always exits 0 and reports failures as a single line
# of stdout rather than via returncode/stderr -- _CLI_NOT_RUNNING_RE below is
# the one exception, the CLI's own inability to reach Obsidian at all.
_NOTE_NOT_FOUND_RE = re.compile(r'^Error: File "(?P<path>.+)" not found\.$')
_VAULT_NOT_FOUND_RE = re.compile(r"^Vault not found\.$")
_CLI_DISABLED_RE = re.compile(
    r"^Command line interface is not enabled\. "
    r"Please turn it on in Settings > General > Advanced\.$"
)
_COMMAND_NOT_FOUND_RE = re.compile(
    r'^Error: Command "(?P<command>[^"]+)" not found\.'
    r"(?: It may require a plugin to be enabled\.| Did you mean: [^\n]*)?$"
)
_GENERIC_ERROR_RE = re.compile(r"^Error: .+$")
_CREATE_RESULT_RE = re.compile(r"^(?:Created|Overwrote): (?P<path>.+)$", re.MULTILINE)
# Commands whose successful stdout is user data (note bodies, vault-relative
# paths, search hits), where a line like "Error: …" may be the data itself.
# Only the specific known failure shapes are classified for these.
_DATA_COMMANDS = frozenset({"read", "daily:read", "files", "search:context", "search"})

_CLI_DISABLED_MESSAGE = (
    "Obsidian's command line interface is disabled. Enable it in Obsidian: "
    'Settings > General > Advanced > "Command line interface".'
)

_VAULT_NOT_FOUND_MESSAGE = (
    "Vault not found. Set OBSIDIAN_VAULT to a registered vault name or id, "
    "or open the target vault in Obsidian."
)

# The CLI's own "cannot reach Obsidian at all" failure -- unlike every shape
# above, reported via stderr with a non-zero exit code (see _run_once).
_CLI_NOT_RUNNING_RE = re.compile(r"^The CLI is unable to find Obsidian\b.*$")


def _classify_stdout_error(
    output: str, args: tuple[str, ...], command: list[str]
) -> ObsidianCLIError | None:
    """Classify a whole-output stdout error line from a successful (exit 0) run.

    Matching is against the ENTIRE trimmed output, never a substring: a
    note's own content may legitimately contain text that looks like one
    of these messages, and only a whole-line match can tell that apart
    from a real CLI-reported failure.

    Sentinel shapes the CLI can only ever emit as a failure -- disabled,
    vault-not-found, and "command not found" for the command we actually
    invoked -- are classified for every command, data commands included:
    none of them can double as legitimate note/search/listing content.
    The generic "Error: " rule stays exempt for data commands (whose
    output can legitimately start with that text) and now matches only
    the first line, so a multi-line "Error: ..." / "Usage: ..." payload
    is still caught for non-data commands.
    """
    stripped = output.strip()

    not_found = _NOTE_NOT_FOUND_RE.match(stripped)
    if not_found:
        target = next((arg.removeprefix("path=") for arg in args if arg.startswith("path=")), None)
        if not_found.group("path") == target:
            return NoteNotFoundError(not_found.group("path"), command=command)

    if _CLI_DISABLED_RE.match(stripped):
        return ObsidianCLIError(returncode=0, stderr=_CLI_DISABLED_MESSAGE, command=command)

    if _VAULT_NOT_FOUND_RE.match(stripped):
        return ObsidianCLIError(returncode=0, stderr=_VAULT_NOT_FOUND_MESSAGE, command=command)

    # Deliberately classified even for data commands. The residual false
    # positive -- a note whose ENTIRE body is this exact line, naming the very
    # command being invoked -- is vanishingly rare and fails loudly. Deciding
    # it by "the retry returned the same text" would not work: a slow vault
    # boot repeats the payload too, and mistaking that for note content is the
    # sentinel-served-as-data bug this rule exists to prevent.
    command_not_found = _COMMAND_NOT_FOUND_RE.match(stripped)
    if command_not_found and args and command_not_found.group("command") == args[0]:
        return ObsidianCLIError(returncode=0, stderr=stripped, command=command)

    # For data commands the whole output can legitimately be text starting with
    # "Error: ", so only the specific shapes above classify there, and only the
    # first line is checked so a multi-line note body isn't falsely matched.
    first_line = stripped.split("\n", 1)[0]
    if args and args[0] not in _DATA_COMMANDS and _GENERIC_ERROR_RE.match(first_line):
        return ObsidianCLIError(returncode=0, stderr=stripped, command=command)

    return None


def _is_obsidian_app_launcher(path: str) -> bool:
    """Return whether path points at the Electron app launcher."""
    resolved = Path(path).resolve()
    parts = [part.casefold() for part in resolved.parts]
    return (
        len(parts) >= 3
        and parts[-3:] == ["contents", "macos", "obsidian"]
        and any(part.endswith(".app") for part in parts)
    )


def _is_executable_file(path: Path) -> bool:
    """Return whether the current process can execute a regular file."""
    return path.is_file() and os.access(path, os.X_OK)


def _resolve_cli_candidate(path: str) -> str:
    """Validate a discovered executable and prefer a real bundled CLI."""
    candidate = Path(path)
    if not _is_executable_file(candidate):
        raise CLINotFoundError(searched_paths=str(path))

    if not _is_obsidian_app_launcher(path):
        return str(candidate)

    sibling = candidate.resolve().with_name("obsidian-cli")
    if _is_executable_file(sibling):
        return str(sibling)

    raise CLINotFoundError(
        searched_paths=(
            f"{path} (Electron app launcher; install/register the real "
            "obsidian-cli binary or set OBSIDIAN_CLI_PATH)"
        )
    )


def _validate_explicit_cli_path(path: str) -> str:
    """Reject the Electron launcher while preserving wrapper overrides."""
    validation_path = shutil.which(path) if not os.path.dirname(path) else path
    if validation_path and _is_obsidian_app_launcher(validation_path):
        return _resolve_cli_candidate(validation_path)
    return path


def find_cli_binary() -> str:
    """Locate and validate the Obsidian CLI binary."""
    env_path = os.environ.get("OBSIDIAN_CLI_PATH")
    if env_path:
        return _resolve_cli_candidate(env_path)

    found_cli = shutil.which("obsidian-cli")
    if found_cli:
        return _resolve_cli_candidate(found_cli)

    found = shutil.which("obsidian")
    if found:
        return _resolve_cli_candidate(found)

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
        timeout: float = 15.0,
    ):
        self.cli_path = cli_path
        self.vault = vault if vault is not None else os.environ.get("OBSIDIAN_VAULT")
        self.timeout = timeout

    async def _run_once(
        self, cmd: list[str], args: tuple[str, ...], effective_timeout: float
    ) -> str:
        """Launch one CLI subprocess, wait for it, and classify the result.

        Raises the same exceptions `_run` documents; the retry lives there.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise CLINotFoundError(searched_paths=f"cli_path={cmd[0]}") from exc

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
            if _CLI_NOT_RUNNING_RE.match(stderr_text):
                raise ObsidianNotRunningError()
            raise ObsidianCLIError(
                returncode=proc.returncode,
                stderr=stderr_text,
                command=cmd,
            )

        decoded_stdout = stdout.decode()
        if _OBSIDIAN_APP_PREAMBLE_RE.match(decoded_stdout.lstrip("\r\n")):
            raise ObsidianCLIError(
                returncode=proc.returncode or 0,
                stderr=_OBSIDIAN_APP_PREAMBLE_MESSAGE,
                command=cmd,
            )

        error = _classify_stdout_error(decoded_stdout, args, cmd)
        if error is not None:
            raise error
        return decoded_stdout

    async def _run(self, *args: str, timeout: float | None = None) -> str:
        """Execute a CLI command and return stdout.

        Retries once, after a short delay, if the CLI reports the command
        we just invoked as "not found" -- see the comment below for why
        that's a known race rather than a real failure.

        Args:
            *args: CLI command arguments (e.g., "read", 'path="test.md"').
            timeout: Override default timeout in seconds.

        Returns:
            Decoded stdout string.

        Raises:
            ObsidianCLIError: On non-zero exit, unexpected stderr, or a
                recognized stdout error line -- the CLI reports
                application-level failures as a line of stdout with exit 0.
            ObsidianNotRunningError: When the CLI reports it cannot reach a
                running Obsidian instance at all.
            NoteNotFoundError: When stdout reports the targeted note missing.
        """
        cli_path = self.cli_path
        if cli_path is None:
            cli_path = find_cli_binary()
            self.cli_path = cli_path
        else:
            cli_path = _validate_explicit_cli_path(cli_path)

        cmd = [cli_path]
        if self.vault:
            cmd.append(f"vault={self.vault}")
        cmd.extend(args)

        effective_timeout = timeout if timeout is not None else self.timeout

        try:
            return await self._run_once(cmd, args, effective_timeout)
        except ObsidianCLIError as exc:
            retry_match = _COMMAND_NOT_FOUND_RE.match(exc.stderr)
            if not args or not retry_match or retry_match.group("command") != args[0]:
                raise
            # Obsidian registers each command's CLI handler asynchronously
            # while a cold vault window boots. The first command that
            # triggers that open can reach the CLI server before its own
            # handler finishes registering and gets misreported as "not
            # found" -- one short retry clears the race. Bounded to a
            # single retry so a genuinely unknown command still fails fast.
            await asyncio.sleep(0.75)
            return await self._run_once(cmd, args, effective_timeout)

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
