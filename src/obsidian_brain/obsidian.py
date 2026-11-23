"""Transport to a running Obsidian: locate the CLI, run it, and call `eval` with JSON in/out.

Every vault operation is a snippet of JavaScript run inside Obsidian through
`obsidian eval`, so it uses the plugin API (`app.vault`, `app.metadataCache`, ...)
rather than the CLI's text commands. `ObsidianCLI.eval` wraps the snippet in a
fixed envelope: the payload goes in as one JSON literal, the result comes back as
one JSON line, and a thrown error carries a `code` that maps to a typed exception.

Every subprocess runs with list-form argv (never a shell), stdin closed, and an
explicit timeout; a timed-out or cancelled call kills and reaps its child.
"""

import asyncio
import contextlib
import errno
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import anyio

from .exceptions import (
    CLINotFoundError,
    CLITimeoutError,
    ContentTooLargeError,
    HeadingNotFoundError,
    InvalidArgumentError,
    NoteExistsError,
    NoteNotFoundError,
    ObsidianCLIError,
    ObsidianError,
    ObsidianNotRunningError,
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

# The real Obsidian CLI exits 0 and reports failures as a single line of stdout
# rather than via returncode/stderr; _CLI_NOT_RUNNING_RE below is the one
# exception, the CLI's own inability to reach Obsidian at all.
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

_CLI_DISABLED_MESSAGE = (
    "Obsidian's command line interface is disabled. Enable it in Obsidian: "
    'Settings > General > Advanced > "Command line interface".'
)

_VAULT_NOT_FOUND_MESSAGE = (
    "Vault not found. Set OBSIDIAN_VAULT to a registered vault name or id, "
    "or open the target vault in Obsidian."
)

# When several CLI processes run at once, Obsidian echoes `Received CLI command [...]` (the
# whole argv, payload included) to stdout ahead of the real result. It is noise: dropped.
_CLI_ECHO_RE = re.compile(r"^Received CLI command .*(?:\n|$)", re.MULTILINE)

# The CLI's own "cannot reach Obsidian at all" failure -- unlike every shape
# above, reported via stderr with a non-zero exit code (see _run_once).
_CLI_NOT_RUNNING_RE = re.compile(r"^The CLI is unable to find Obsidian\b.*$")

# Largest JSON payload one call carries. The whole `code=` argv entry must fit the
# OS argument limit (~1,040,000 bytes on macOS, with the environment counting too);
# the fixed JS around the payload adds a few KB, so this keeps a safe margin.
MAX_PAYLOAD_BYTES = 900_000

# Pause before the one retry of a cold-start "command not found" (see ObsidianCLI.run).
_COLD_START_RETRY_DELAY = 0.75

# Raw BOM / line-separator characters are legal JSON but risky in argv and JS source.
_ESCAPE = {0xFEFF: "\\ufeff", 0x2028: "\\u2028", 0x2029: "\\u2029"}

# Longest slice of CLI output echoed into an error message.
_MAX_ERROR_OUTPUT = 500

# How eval error codes (`e.code` thrown from the JS) map to exceptions.
_EVAL_ERRORS: dict[str, type[ObsidianError]] = {
    "NOT_FOUND": NoteNotFoundError,
    "EXISTS": NoteExistsError,
    "HEADING_NOT_FOUND": HeadingNotFoundError,
    "INVALID": InvalidArgumentError,
}

# `await run()` rather than `await (async () => {...})()`: `eval` first tries the code
# as a plain script and only falls back to an async function body when that fails with
# an await error, and `await (...)` parses as a plain call to a function named `await`.
# An error message never carries the vault's absolute path (Node's OS errors do: ENAMETOOLONG,
# EACCES, ...): it is cut out, which leaves the vault-relative path.
_EVAL_TEMPLATE = (
    "const run = async () => {\n%s\n}; "
    "try { const value = await run(); "
    "return JSON.stringify({ok: true, value: value ?? null}); } "
    "catch (e) { const base = app.vault?.adapter?.basePath; let message = String(e?.message ?? e); "
    "if (base) message = message.split(base + '/').join('').split(base).join(''); "
    "return JSON.stringify({ok: false, error: {code: e?.code ?? null, message}}); }"
)


def _cap(text: str) -> str:
    """Trim CLI output to what is safe and useful inside an error message."""
    text = text.strip()
    return text if len(text) <= _MAX_ERROR_OUTPUT else text[:_MAX_ERROR_OUTPUT] + "..."


def _classify_stdout_error(output: str, args: tuple[str, ...]) -> ObsidianCLIError | None:
    """Classify a whole-output stdout error line from a successful (exit 0) run.

    Matching is against the ENTIRE trimmed output, never a substring. The CLI's
    machine-readable output (`eval` results start with `=> `, `format=json`
    starts with `[` or `{`) cannot be mistaken for these error lines, so every
    command is classified the same way.
    """
    stripped = output.strip()

    if _CLI_DISABLED_RE.match(stripped):
        return ObsidianCLIError(_CLI_DISABLED_MESSAGE)

    if _VAULT_NOT_FOUND_RE.match(stripped):
        return ObsidianCLIError(_VAULT_NOT_FOUND_MESSAGE)

    command_not_found = _COMMAND_NOT_FOUND_RE.match(stripped)
    if command_not_found and args and command_not_found.group("command") == args[0]:
        return ObsidianCLIError(_cap(stripped))

    first_line = stripped.split("\n", 1)[0]
    if args and _GENERIC_ERROR_RE.match(first_line):
        return ObsidianCLIError(_cap(stripped))

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


class ObsidianCLI:
    """Runs Obsidian CLI commands and `eval` snippets.

    Args:
        cli_path: Optional binary path. Discovery is deferred until the first command.
        vault: Optional vault name. Defaults to OBSIDIAN_VAULT when unset.
        timeout: Default timeout in seconds for one CLI call.
    """

    def __init__(
        self,
        cli_path: str | None = None,
        vault: str | None = None,
        timeout: float = 20.0,
    ):
        self.cli_path = cli_path
        self.vault = vault if vault is not None else os.environ.get("OBSIDIAN_VAULT")
        self.timeout = timeout

    async def _run_once(self, cmd: list[str], command: str, timeout: float) -> str:
        """Launch one CLI subprocess, wait for it, and return its stdout.

        Raises CLITimeoutError on timeout and on any other failure the CLI reports
        through stderr or the exit code. The child is always killed and reaped
        before this returns or raises, including when the caller is cancelled.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise CLINotFoundError(searched_paths=f"cli_path={cmd[0]}") from exc
        except OSError as exc:
            if exc.errno == errno.E2BIG:
                raise ContentTooLargeError(
                    "The request is too large for one Obsidian CLI call. "
                    "Send less content per call."
                ) from exc
            raise ObsidianCLIError(f"Could not start the Obsidian CLI: {exc.strerror}.") from exc

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            raise CLITimeoutError(timeout=timeout, command=command) from None
        finally:
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                # Shielded: a cancelled caller (anyio scopes re-cancel every await)
                # must still wait out the killed child, or it stays a zombie.
                with anyio.CancelScope(shield=True):
                    await proc.wait()

        stderr_text = stderr.decode(errors="replace").strip()
        if proc.returncode != 0 or stderr_text:
            if _CLI_NOT_RUNNING_RE.match(stderr_text):
                raise ObsidianNotRunningError()
            raise ObsidianCLIError(
                f"obsidian {command} failed (exit {proc.returncode}): {_cap(stderr_text)}"
            )

        decoded_stdout = _CLI_ECHO_RE.sub("", stdout.decode(errors="replace"))
        if _OBSIDIAN_APP_PREAMBLE_RE.match(decoded_stdout.lstrip("\r\n")):
            raise ObsidianCLIError(_OBSIDIAN_APP_PREAMBLE_MESSAGE)
        return decoded_stdout

    async def _attempt(self, cmd: list[str], command: str, timeout: float, idempotent: bool) -> str:
        """`_run_once`, repeated once on timeout when the command is safe to repeat.

        Obsidian occasionally executes a CLI command but never answers it (about 1 call in
        800 under load, measured: the command's effect is visible, the CLI waits forever).
        Repeating a read or an idempotent edit is harmless; anything else must not be repeated.
        """
        try:
            return await self._run_once(cmd, command, timeout)
        except CLITimeoutError:
            if not idempotent:
                raise
            return await self._run_once(cmd, command, timeout)

    async def run(self, *args: str, timeout: float | None = None, idempotent: bool = False) -> str:
        """Execute a CLI command and return stdout.

        For machine-readable commands (`eval`, anything with `format=json`):
        stdout shaped like an error line is raised, never returned as data.
        Retries once, after a short delay, if the CLI reports the command we
        just invoked as "not found" -- see the comment below for why that is a
        known race rather than a real failure.

        Args:
            *args: CLI command arguments, e.g. `"eval", "code=..."`.
            timeout: Override the default timeout in seconds.
            idempotent: The command is safe to repeat; a timed-out call is retried once.

        Raises:
            ObsidianCLIError: Non-zero exit, unexpected stderr, CLI disabled,
                vault not found, or a recognized stdout error line.
            ObsidianNotRunningError: The CLI cannot reach a running Obsidian.
            CLITimeoutError: The command did not finish in time.
            CLINotFoundError: The CLI binary cannot be located.
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
        command = args[0] if args else ""

        output = await self._attempt(cmd, command, effective_timeout, idempotent)
        error = _classify_stdout_error(output, args)
        not_found = _COMMAND_NOT_FOUND_RE.match(output.strip())
        if error is not None and not_found and not_found.group("command") == command:
            # Obsidian registers each command's CLI handler asynchronously
            # while a cold vault window boots. The first command that
            # triggers that open can reach the CLI server before its own
            # handler finishes registering and gets misreported as "not
            # found" -- one short retry clears the race. Bounded to a
            # single retry so a genuinely unknown command still fails fast.
            await asyncio.sleep(_COLD_START_RETRY_DELAY)
            output = await self._attempt(cmd, command, effective_timeout, idempotent)
            error = _classify_stdout_error(output, args)
        if error is not None:
            raise error
        return output

    async def eval(
        self,
        body: str,
        payload: object = None,
        timeout: float | None = None,
        idempotent: bool = False,
    ) -> Any:
        """Run a JavaScript function body inside Obsidian and return its JSON value.

        `body` runs as an async function body (so `await` and `return` work) with
        the JSON-encoded `payload` bound to the constant `input`. Throw an Error
        with a `code` of NOT_FOUND, EXISTS, HEADING_NOT_FOUND or INVALID to raise
        the matching exception; any other thrown error raises ObsidianCLIError. Pass
        `idempotent=True` only when running the body twice leaves the same result.

        Raises:
            ContentTooLargeError: The encoded payload exceeds MAX_PAYLOAD_BYTES.
            ObsidianError: As documented on `run`, plus the mapped eval errors.
        """
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).translate(_ESCAPE)
        try:
            size = len(encoded.encode("utf-8"))
        except UnicodeEncodeError:
            raise InvalidArgumentError(
                "Content contains a lone surrogate and cannot be encoded as UTF-8."
            ) from None
        if size > MAX_PAYLOAD_BYTES:
            raise ContentTooLargeError(
                f"Content is {size // 1000} KB; one Obsidian CLI call carries at most "
                f"{MAX_PAYLOAD_BYTES // 1000} KB. Split it across several calls or notes."
            )

        code = f"const input = {encoded}; " + _EVAL_TEMPLATE % body
        output = (
            await self.run("eval", f"code={code}", timeout=timeout, idempotent=idempotent)
        ).strip()
        if not output.startswith("=> "):
            raise ObsidianCLIError(f"Unexpected output from obsidian eval: {_cap(output)}")
        try:
            envelope = json.loads(output[3:])
            ok = envelope["ok"]
        except (ValueError, KeyError, TypeError):
            raise ObsidianCLIError(
                f"Unreadable result from obsidian eval: {_cap(output)}"
            ) from None
        if ok:
            return envelope.get("value")
        error = envelope.get("error") or {}
        message = str(error.get("message") or "unknown error")
        error_code = error.get("code")  # whatever the JS threw: only a string maps to an error
        raise _EVAL_ERRORS.get(error_code if isinstance(error_code, str) else "", ObsidianCLIError)(
            _cap(message)
        )
