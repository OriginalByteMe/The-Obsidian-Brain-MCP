"""Transport to a running Obsidian: locate the CLI, run it, and call `eval` with JSON in/out.

Every vault operation is a snippet of JavaScript run inside Obsidian through
`obsidian eval`, so it uses the plugin API (`app.vault`, `app.metadataCache`, ...)
rather than the CLI's text commands. `ObsidianCLI.eval` sends each snippet to a window once,
installs it there as a function, and calls it afterwards with a short command: the payload goes
in as one JSON literal, the result comes back as one JSON line, and a thrown error carries a
`code` that maps to a typed exception. Evals run one at a time (see `MAX_EVALS_IN_FLIGHT`).
Obsidian sometimes runs a call and never answers it; every eval carries a request id, the window
remembers what became of it, and a call that has no reply after a short grace asks the window
(see `REPLY_GRACE`) instead of waiting out the timeout.

Every subprocess runs with list-form argv (never a shell), stdin closed, and an
explicit timeout; a timed-out or cancelled call kills and reaps its child.
"""

import asyncio
import contextlib
import errno
import functools
import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Callable
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
# the code around the payload (a call, or a snippet to install) adds at most a few tens of KB,
# so this keeps a safe margin.
MAX_PAYLOAD_BYTES = 900_000

# How many `obsidian eval` calls one ObsidianCLI keeps in flight. Obsidian's eval command swaps
# `console.log`/`warn`/`error` for the length of each call and then puts back what it found.
# When two calls overlap and the first one ends first, the second puts back the first one's
# swap, which then stays installed for good: every later console message of the window (each CLI
# command logs its whole argv) is kept in that swap's buffer until the window reloads, and each
# overlap that ends out of order adds one more swap. A minimized window overlaps the most calls:
# 1,075 calls through the server left 13-33 MB behind (4-9 swaps) when each call carried the whole
# helper code and up to 150 ran at once, 4-7 MB (6-15 swaps) with short calls two or four at a
# time, and about 2 MB (no swap) one at a time. Other processes sending evals to the same vault
# can still overlap with ours.
MAX_EVALS_IN_FLIGHT = 1

# How long an `eval` may go without a reply before the window is asked what became of it, and how
# often it is asked again while the call is still running. Obsidian runs some calls and never
# answers them (counted inside the window: 5 of 4,500 sequential calls on two windows, about 1 in
# 900, and more under load; every one had run, none was answered late, and the CLI waits for its
# reply forever). Calls that are answered take a median of 11-22 ms, 99% under 0.35 s, the slowest
# 0.87 s. Asking early is harmless: a call that is merely slow is reported as running and waited for.
REPLY_GRACE = 2.0

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

# What `eval` installs in a window, once, under `window.__brain`: `run(key, input, id)` calls the
# function stored under `key` and returns the answer as one JSON string. A new text of this
# runner changes `rev`, so a window that holds an older one gets it replaced (and the functions
# installed with it dropped). An error message never carries the vault's absolute path (Node's
# OS errors do: ENAMETOOLONG, EACCES, ...): it is cut out, which leaves the vault-relative path.
# `window.__brainReqs` (it outlives a replaced runner) remembers every request id: `running`, or
# `done` with the answer, so a call whose reply never reached the CLI can be asked for (_ASK). An
# id that is already known never starts: that is what makes a cancelled id safe to send again
# under a new one. The log is bounded: 128 entries, none older than 2 minutes once finished (a
# call still running is never dropped), and an answer over 128 KB is not kept (`answer: null`).
_RUNNER = """\
if (window.__brain?.rev !== '@REV@') {
  window.__brain = {
    rev: '@REV@',
    fns: {},
    async run(key, input, id) {
      const reqs = (window.__brainReqs ??= new Map());
      if (reqs.has(id)) return '{"ok":false,"cancelled":true}';
      reqs.set(id, {state: 'running'});
      let answer;
      try {
        answer = JSON.stringify({ok: true, value: (await this.fns[key](input)) ?? null});
      } catch (e) {
        const base = app.vault?.adapter?.basePath;
        let message = String(e?.message ?? e);
        if (base) message = message.split(base + '/').join('').split(base).join('');
        answer = JSON.stringify({ok: false, error: {code: e?.code ?? null, message}});
      }
      reqs.set(id, {state: 'done', at: Date.now(), answer: answer.length <= 131072 ? answer : null});
      for (const [other, req] of reqs) {
        if (req.state === 'running') continue;
        if (reqs.size <= 128 && Date.now() - req.at < 120000) break;
        reqs.delete(other);
      }
      return answer;
    },
  };
}"""
_RUNNER_REV = hashlib.sha256(_RUNNER.encode()).hexdigest()[:12]
_RUNNER = _RUNNER.replace("@REV@", _RUNNER_REV)

# What the server asks the window about a request that has no reply: `running`, `done` (with the
# answer, null when it was too large to keep) or `cancelled`. A request the window has never seen
# is recorded as cancelled by the question itself, so it can never start afterwards; the server
# then sends it again under a new id. Asking twice gives the same answer.
_ASK = """\
(() => {
  const reqs = (window.__brainReqs ??= new Map());
  const req = reqs.get('@ID@') ?? {state: 'cancelled', at: Date.now()};
  reqs.set('@ID@', req);
  return JSON.stringify({state: req.state, answer: req.answer ?? null});
})()"""

# The answer of a call to a function the window does not hold (never installed, window reloaded,
# or another server version replaced the runner).
_MISSING = '{"ok":false,"missing":true}'


@functools.cache
def _function_key(body: str) -> str:
    """The name a body is installed under: it changes with the body and with the runner."""
    return hashlib.sha256(f"{_RUNNER_REV}\n{body}".encode()).hexdigest()[:16]


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


class _NeverRan(Exception):
    """The window has not run a request and, now that it was asked, never will (see `_ASK`)."""


class ObsidianCLI:
    """Runs Obsidian CLI commands and `eval` snippets.

    Args:
        cli_path: Optional binary path. Discovery is deferred until the first command.
        vault: Optional vault name. Defaults to OBSIDIAN_VAULT when unset.
        timeout: Default timeout in seconds for one CLI call.
        max_evals: How many `eval` calls may run at once (see MAX_EVALS_IN_FLIGHT); the others
            wait their turn, and the wait does not count against `timeout`.
        reply_grace: Seconds an `eval` may go without a reply before the window is asked what
            became of it (see REPLY_GRACE). A call whose `timeout` is no longer than this is
            never asked about.
    """

    def __init__(
        self,
        cli_path: str | None = None,
        vault: str | None = None,
        timeout: float = 20.0,
        max_evals: int = MAX_EVALS_IN_FLIGHT,
        reply_grace: float = REPLY_GRACE,
    ):
        self.cli_path = cli_path
        self.vault = vault if vault is not None else os.environ.get("OBSIDIAN_VAULT")
        self.timeout = timeout
        self.reply_grace = reply_grace
        self._eval_slots = asyncio.Semaphore(max_evals)
        # One question about a request at a time: questions overlapping each other (and the
        # call they are about) could end out of order and leave a console swap behind.
        self._questions = asyncio.Lock()
        # The snippets this window is believed to hold, so a repeat call can skip sending them.
        # Only a hint: a reloaded window answers `_MISSING` and gets the snippet again.
        self._installed: set[str] = set()

    def _command(self, args: tuple[str, ...]) -> list[str]:
        """The argv of one CLI call: the binary (found the first time), the vault, then `args`."""
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
        return cmd

    async def _run_once(
        self,
        cmd: list[str],
        command: str,
        timeout: float,
        request_id: str | None = None,
        deadline: float | None = None,
    ) -> str:
        """Launch one CLI subprocess, wait for it, and return its stdout.

        `request_id` is the id an `eval`'s code carries: a call with no reply after
        `reply_grace` asks the window what became of it (see `_wait`), and the answer of a call
        that finished without being answered is returned as if the CLI had printed it.
        `deadline` (a loop time, `now + timeout` by default) ends the wait.

        Raises CLITimeoutError on timeout and on any other failure the CLI reports
        through stderr or the exit code, `_NeverRan` when the window never ran the request.
        The child is always killed and reaped before this returns or raises, including when
        the caller is cancelled.
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

        reply = asyncio.ensure_future(proc.communicate())
        if deadline is None:
            deadline = asyncio.get_running_loop().time() + timeout
        recovered: str | None = None
        try:
            recovered = await self._wait(reply, command, timeout, request_id, deadline)
        finally:
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                # Shielded: a cancelled caller (anyio scopes re-cancel every await)
                # must still wait out the killed child, or it stays a zombie.
                with anyio.CancelScope(shield=True):
                    await proc.wait()
            reply.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.wait({reply})
        if recovered is not None:
            return f"=> {recovered}"

        stdout, stderr = reply.result()
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

    async def _wait(
        self,
        reply: asyncio.Future[tuple[bytes, bytes]],
        command: str,
        timeout: float,
        request_id: str | None,
        deadline: float,
    ) -> str | None:
        """Wait for the CLI child's reply; None once it has come.

        Obsidian runs some calls and never answers them, and the CLI waits forever. A call with
        a `request_id` that has no reply after `reply_grace` is therefore not just waited for:
        the window is asked about it. Finished: its answer is returned and the caller kills the
        child. Still running: it is waited for and asked about again every `reply_grace`, up to
        the deadline. Never ran: `_NeverRan`, and the window has marked the id cancelled, so it
        cannot start later.
        """
        loop = asyncio.get_running_loop()
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise CLITimeoutError(timeout=timeout, command=command)
            patience = remaining if request_id is None else min(remaining, self.reply_grace)
            await asyncio.wait({reply}, timeout=patience)
            if reply.done():
                return None
            remaining = deadline - loop.time()
            if request_id is None or remaining <= 0:
                continue
            asked = await self._ask(request_id, min(self.reply_grace, remaining))
            if reply.done():
                return None
            if asked is None:  # the question went unanswered too: ask again
                continue
            state, answer = asked
            if state == "cancelled":
                raise _NeverRan
            if state == "done":
                if answer is None:  # it ran, but its answer was too large for the window to keep
                    elapsed = timeout - (deadline - loop.time())
                    raise CLITimeoutError(timeout=round(elapsed, 1), command=command)
                return answer

    async def _ask(self, request_id: str, timeout: float) -> tuple[str, str | None] | None:
        """What became of a request, as `(state, answer)` (see `_ASK`); None if unanswered."""
        cmd = self._command(("eval", f"code={_ASK.replace('@ID@', request_id)}"))
        async with self._questions:
            try:
                output = await self._run_once(cmd, "eval", timeout)
            except CLITimeoutError:
                return None
        text = output.strip()
        try:
            if not text.startswith("=> "):
                raise ValueError
            reply = json.loads(text[3:])
            state, answer = reply["state"], reply["answer"]
            if state not in ("running", "done", "cancelled") or not (
                answer is None or isinstance(answer, str)
            ):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise ObsidianCLIError(
                f"Unreadable reply to a question about a request: {_cap(text)}"
            ) from None
        return state, answer

    async def _request(
        self,
        args_for: Callable[[str], tuple[str, ...]],
        command: str,
        timeout: float,
        tracked: bool,
    ) -> str:
        """One CLI call. A tracked one (an `eval` whose code carries the id it is given) is sent
        again under a new id when the window turns out never to have run it."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            request_id = uuid.uuid4().hex[:16] if tracked else None
            cmd = self._command(args_for(request_id or ""))
            try:
                return await self._run_once(cmd, command, timeout, request_id, deadline)
            except _NeverRan:
                if loop.time() >= deadline:
                    raise CLITimeoutError(timeout=timeout, command=command) from None

    async def _attempt(
        self,
        args_for: Callable[[str], tuple[str, ...]],
        command: str,
        timeout: float,
        idempotent: bool,
        tracked: bool,
    ) -> str:
        """`_request`, repeated once on timeout when the command is safe to repeat.

        A reply Obsidian never sends is recovered long before the timeout for an `eval` (see
        `_wait`); for any other command, and for an `eval` the window cannot be asked about
        (it does not answer at all, or its answer was too large to keep), the call waits out the
        timeout. Repeating a read or an idempotent edit is then harmless; anything else must
        not be repeated. An `eval` holds its slot through the repeat: nothing else runs in the
        window before it.
        """
        slot = self._eval_slots if command == "eval" else contextlib.nullcontext()
        async with slot:
            try:
                return await self._request(args_for, command, timeout, tracked)
            except CLITimeoutError:
                if not idempotent:
                    raise
                return await self._request(args_for, command, timeout, tracked)

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
        return await self._run(args, lambda _: args, timeout, idempotent, tracked=False)

    async def _run(
        self,
        args: tuple[str, ...],
        args_for: Callable[[str], tuple[str, ...]],
        timeout: float | None,
        idempotent: bool,
        tracked: bool,
    ) -> str:
        """`run` for a call whose arguments depend on its request id (see `_request`).

        `args` are the arguments as far as classifying the output needs them: the command name.
        `tracked` says `args_for` puts the request id it is given into the call, so that a reply
        that never arrives can be recovered.
        """
        effective_timeout = timeout if timeout is not None else self.timeout
        command = args[0] if args else ""

        output = await self._attempt(args_for, command, effective_timeout, idempotent, tracked)
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
            output = await self._attempt(args_for, command, effective_timeout, idempotent, tracked)
            error = _classify_stdout_error(output, args)
        if error is not None:
            raise error
        return output

    async def _send(
        self, code_for: Callable[[str], str], timeout: float | None, idempotent: bool
    ) -> dict[str, Any]:
        """Run one `eval` and parse its output into the envelope `{ok, value | error}`.

        `code_for` makes the code for a request id: the id goes into the call, and a call the
        window never ran is sent again under a new one (see `_wait`).
        """
        output = (
            await self._run(
                ("eval",),
                lambda request_id: ("eval", f"code={code_for(request_id)}"),
                timeout,
                idempotent,
                tracked=True,
            )
        ).strip()
        if not output.startswith("=> "):
            raise ObsidianCLIError(f"Unexpected output from obsidian eval: {_cap(output)}")
        try:
            envelope: dict[str, Any] = json.loads(output[3:])
            envelope["ok"]  # KeyError or TypeError when the JSON is not an envelope
        except (ValueError, KeyError, TypeError):
            raise ObsidianCLIError(
                f"Unreadable result from obsidian eval: {_cap(output)}"
            ) from None
        return envelope

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

        The body is installed in the window as a function the first time it is sent and stays
        there, so every later call carries only the payload. That makes the body a constant: one
        built from data would install a new function for every value. Data goes in the payload.

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

        # Both call forms are a single expression: `eval` evaluates a plain statement list as a
        # script, where a top-level `return` is a syntax error.
        key = _function_key(body)
        envelope: dict[str, Any] | None = None
        if key in self._installed:
            envelope = await self._send(
                lambda rid: f"window.__brain?.fns['{key}'] ? window.__brain.run('{key}', {encoded}, '{rid}') "
                f": '{_MISSING}'",
                timeout,
                idempotent,
            )
            if envelope.get("missing") is True:  # the window was reloaded or got another runner
                self._installed.discard(key)
                envelope = None
        if envelope is None:
            envelope = await self._send(
                lambda rid: f"(() => {{\n{_RUNNER}\n"
                f"window.__brain.fns['{key}'] ??= async (input) => {{\n{body}\n}};\n"
                f"return window.__brain.run('{key}', {encoded}, '{rid}');\n}})()",
                timeout,
                idempotent,
            )
            self._installed.add(key)
        if envelope["ok"]:
            return envelope.get("value")
        error = envelope.get("error") or {}
        message = str(error.get("message") or "unknown error")
        error_code = error.get("code")  # whatever the JS threw: only a string maps to an error
        raise _EVAL_ERRORS.get(error_code if isinstance(error_code, str) else "", ObsidianCLIError)(
            _cap(message)
        )
