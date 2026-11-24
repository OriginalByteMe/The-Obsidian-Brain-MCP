"""Transport tests: binary discovery, subprocess handling, sentinels and the eval envelope.

A tiny executable stands in for the Obsidian CLI. Its behaviour comes from FAKE_* env
vars and every call's argv is appended to a JSON-lines file, so each test asserts on the
real process boundary instead of mocks.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any
from unittest.mock import patch

import anyio
import pytest

from obsidian_brain import obsidian
from obsidian_brain.exceptions import (
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
from obsidian_brain.obsidian import MAX_PAYLOAD_BYTES, ObsidianCLI, find_cli_binary
from obsidian_brain.vault import Vault, _snippet, get_vault

FAKE_CLI = f"""#!{sys.executable}
import json, os, sys, time

with open(os.environ["FAKE_CALLS"], "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_PIDFILE"):
    with open(os.environ["FAKE_PIDFILE"], "w") as f:
        f.write(str(os.getpid()))
# FAKE_FIRST_STDOUT / FAKE_FIRST_SLEEP apply to the first call only (counted in a file, replaced
# atomically so that processes running at the same time never read it half written).
counter = os.environ["FAKE_CALLS"] + ".count"
n = int(open(counter).read()) + 1 if os.path.exists(counter) else 1
open(f"{{counter}}.{{os.getpid()}}", "w").write(str(n))
os.replace(f"{{counter}}.{{os.getpid()}}", counter)
first_sleep = os.environ.get("FAKE_FIRST_SLEEP") if n == 1 else None
started = time.time()
time.sleep(float(first_sleep or os.environ.get("FAKE_SLEEP", "0")))
if os.environ.get("FAKE_SPANS"):  # when this process ran: the span overlap tests read it back
    with open(os.environ["FAKE_SPANS"], "a", encoding="utf-8") as f:
        f.write(json.dumps([started, time.time()]) + "\\n")
stdout = os.environ.get("FAKE_FIRST_STDOUT") if n == 1 else None
if stdout is None:
    stdout = os.environ.get("FAKE_STDOUT", "")
if os.environ.get("FAKE_REPORT_STDIN"):
    devnull = os.path.samestat(os.fstat(0), os.stat(os.devnull))
    stdout = "=> " + json.dumps({{"ok": True, "value": devnull}})
sys.stdout.write(stdout)
sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
raise SystemExit(int(os.environ.get("FAKE_EXIT", "0")))
"""


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An executable CLI double, plus helpers to script it and read back what it saw."""
    executable = tmp_path / "obsidian-fake"
    executable.write_text(FAKE_CLI)
    executable.chmod(0o755)
    calls = tmp_path / "calls.jsonl"
    for name in list(os.environ):
        if name.startswith("FAKE_") or name in {"OBSIDIAN_VAULT", "OBSIDIAN_CLI_PATH"}:
            monkeypatch.delenv(name)
    spans = tmp_path / "spans.jsonl"
    monkeypatch.setenv("FAKE_CALLS", str(calls))
    monkeypatch.setenv("FAKE_SPANS", str(spans))
    monkeypatch.setattr(obsidian, "_COLD_START_RETRY_DELAY", 0)

    class Fake:
        path = str(executable)
        pidfile = tmp_path / "pid"

        def script(self, **env: str) -> None:
            for name, value in env.items():
                monkeypatch.setenv(f"FAKE_{name.upper()}", value)

        def reset(self) -> None:
            for suffix in ("", ".count"):
                Path(str(calls) + suffix).unlink(missing_ok=True)

        def calls(self) -> list[list[str]]:
            return (
                [json.loads(line) for line in calls.read_text().splitlines()]
                if calls.exists()
                else []
            )

        def max_overlap(self) -> int:
            """The most fake CLI processes that were running at the same moment."""
            edges = sorted(
                (t, kind)
                for span in (json.loads(line) for line in spans.read_text().splitlines())
                for t, kind in ((span[0], 1), (span[1], -1))
            )
            running = peak = 0
            for _, kind in edges:
                running += kind
                peak = max(peak, running)
            return peak

        def cli(self, **kwargs) -> ObsidianCLI:
            kwargs.setdefault("vault", "testvault")
            return ObsidianCLI(cli_path=self.path, **kwargs)

        async def pid(self) -> int:
            for _ in range(200):
                if self.pidfile.exists() and self.pidfile.read_text():
                    return int(self.pidfile.read_text())
                await asyncio.sleep(0.02)
            raise AssertionError("fake CLI never started")

    return Fake()


def assert_reaped(pid: int) -> None:
    """A killed child that was never waited on lingers as a zombie; kill(pid, 0) finds it."""
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    path.chmod(0o755)
    return path


def _launcher(tmp_path: Path) -> Path:
    return _executable(tmp_path / "Obsidian.app" / "Contents" / "MacOS" / "Obsidian")


class TestFindCliBinary:
    def test_finds_binary_via_env_var(self, tmp_path):
        binary = _executable(tmp_path / "obsidian")
        with patch.dict(os.environ, {"OBSIDIAN_CLI_PATH": str(binary)}):
            assert find_cli_binary() == str(binary)

    def test_finds_binary_via_which(self, tmp_path):
        binary = _executable(tmp_path / "obsidian")
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("obsidian_brain.obsidian.shutil.which", side_effect=[None, str(binary)]),
        ):
            os.environ.pop("OBSIDIAN_CLI_PATH", None)
            assert find_cli_binary() == str(binary)

    def test_prefers_registered_cli_name(self, tmp_path):
        binary = _executable(tmp_path / "obsidian-cli")
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("obsidian_brain.obsidian.shutil.which", side_effect=[str(binary)]),
        ):
            os.environ.pop("OBSIDIAN_CLI_PATH", None)
            assert find_cli_binary() == str(binary)

    def test_rejects_electron_launcher_override(self, tmp_path):
        launcher = _launcher(tmp_path)
        with (
            patch.dict(os.environ, {"OBSIDIAN_CLI_PATH": str(launcher)}),
            pytest.raises(CLINotFoundError, match="Electron app launcher"),
        ):
            find_cli_binary()

    def test_prefers_sibling_cli_for_electron_launcher(self, tmp_path):
        launcher = _launcher(tmp_path)
        sibling = _executable(launcher.with_name("obsidian-cli"))
        with patch.dict(os.environ, {"OBSIDIAN_CLI_PATH": str(launcher)}):
            assert find_cli_binary() == str(sibling)

    def test_prefers_sibling_cli_for_symlinked_launcher(self, tmp_path):
        launcher = _launcher(tmp_path)
        sibling = _executable(launcher.with_name("obsidian-cli"))
        link = tmp_path / "bin" / "obsidian"
        link.parent.mkdir()
        link.symlink_to(launcher)
        with patch.dict(os.environ, {"OBSIDIAN_CLI_PATH": str(link)}):
            assert find_cli_binary() == str(sibling)

    def test_rejects_file_not_executable_by_current_process(self, tmp_path):
        candidate = _executable(tmp_path / "obsidian")
        with (
            patch.dict(os.environ, {"OBSIDIAN_CLI_PATH": str(candidate)}),
            patch("obsidian_brain.obsidian.os.access", return_value=False),
            pytest.raises(CLINotFoundError),
        ):
            find_cli_binary()

    def test_raises_cli_not_found_error(self):
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("obsidian_brain.obsidian.shutil.which", return_value=None),
        ):
            os.environ.pop("OBSIDIAN_CLI_PATH", None)
            with pytest.raises(CLINotFoundError):
                find_cli_binary()

    def test_env_var_path_not_found(self):
        with (
            patch.dict(os.environ, {"OBSIDIAN_CLI_PATH": "/nonexistent/obsidian"}),
            pytest.raises(CLINotFoundError),
        ):
            find_cli_binary()


class TestCliPathHandling:
    async def test_discovers_cli_lazily_and_puts_env_vault_first(self, fake, monkeypatch):
        monkeypatch.setenv("OBSIDIAN_CLI_PATH", fake.path)
        monkeypatch.setenv("OBSIDIAN_VAULT", "from-env")
        fake.script(stdout="ok")
        cli = ObsidianCLI()  # nothing is looked up at construction
        assert cli.cli_path is None
        assert await cli.run("version") == "ok"
        assert fake.calls() == [["vault=from-env", "version"]]

    async def test_explicit_vault_beats_env(self, fake, monkeypatch):
        monkeypatch.setenv("OBSIDIAN_VAULT", "from-env")
        fake.script(stdout="ok")
        await fake.cli(vault="explicit").run("version")
        assert fake.calls() == [["vault=explicit", "version"]]

    async def test_no_vault_means_no_vault_argument(self, fake):
        fake.script(stdout="ok")
        await ObsidianCLI(cli_path=fake.path).run("version")
        assert fake.calls() == [["version"]]

    async def test_missing_binary_is_reported_on_first_command(self):
        cli = ObsidianCLI(cli_path="/nonexistent/obsidian")
        with pytest.raises(CLINotFoundError):
            await cli.run("version")

    async def test_bare_command_resolving_to_app_launcher_is_rejected(self, tmp_path):
        launcher = _launcher(tmp_path)
        with (
            patch("obsidian_brain.obsidian.shutil.which", return_value=str(launcher)),
            patch("obsidian_brain.obsidian.asyncio.create_subprocess_exec") as spawn,
            pytest.raises(CLINotFoundError, match="Electron app launcher"),
        ):
            await ObsidianCLI(cli_path="obsidian").run("version")
        spawn.assert_not_called()


# ---------------------------------------------------------------------------
# Subprocess handling
# ---------------------------------------------------------------------------


class TestSubprocess:
    async def test_stdin_is_not_inherited(self, fake):
        """The CLI child reads inherited stdin; it must get /dev/null."""
        fake.script(report_stdin="1")
        read_end, write_end = (
            os.pipe()
        )  # make this process's own stdin something other than /dev/null
        saved = os.dup(0)
        os.dup2(read_end, 0)
        try:
            assert await fake.cli().eval("return 1;") is True
        finally:
            os.dup2(saved, 0)
            for fd in (read_end, write_end, saved):
                os.close(fd)

    async def test_argv_is_a_list_with_no_shell(self, fake):
        fake.script(stdout='=> {"ok":true,"value":1}')
        await fake.cli().eval("return 1;", {"text": "$(touch pwned) `x` ; & | > \"q\" 'q'"})
        (argv,) = fake.calls()
        assert argv[:2] == ["vault=testvault", "eval"]
        assert len(argv) == 3 and argv[2].startswith("code=")

    async def test_timeout_raises_and_kills_and_reaps_the_child(self, fake):
        fake.script(sleep="60", pidfile=str(fake.pidfile))
        with pytest.raises(CLITimeoutError) as caught:
            await fake.cli(timeout=1.5).run("eval", "code=x")
        assert "obsidian eval timed out after 1.5s" in str(caught.value)
        assert_reaped(await fake.pid())

    async def test_per_call_timeout_overrides_the_default(self, fake):
        fake.script(sleep="60", pidfile=str(fake.pidfile))
        with pytest.raises(CLITimeoutError):
            await fake.cli(timeout=60).run("eval", "code=x", timeout=1.5)
        assert_reaped(await fake.pid())

    async def test_asyncio_cancellation_kills_and_reaps_the_child(self, fake):
        fake.script(sleep="60", pidfile=str(fake.pidfile))
        task = asyncio.create_task(fake.cli().run("eval", "code=x"))
        pid = await fake.pid()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert_reaped(pid)

    async def test_anyio_cancel_scope_kills_and_reaps_the_child(self, fake):
        """anyio re-cancels every await in a cancelled scope: the reap must be shielded."""
        fake.script(sleep="60", pidfile=str(fake.pidfile))
        with anyio.move_on_after(1.5) as scope:
            await fake.cli().run("eval", "code=x")
        assert scope.cancelled_caught
        assert_reaped(await fake.pid())

    async def test_idempotent_call_is_retried_once_after_a_lost_reply(self, fake):
        """Obsidian sometimes runs a command and never answers: reads are simply repeated."""
        fake.script(first_sleep="60", stdout=_envelope(ok=True, value="fine"))
        assert await fake.cli(timeout=1.5).eval("return 1;", idempotent=True) == "fine"
        assert len(fake.calls()) == 2

    async def test_idempotent_call_gives_up_after_one_retry(self, fake):
        fake.script(sleep="60", first_sleep="60")
        with pytest.raises(CLITimeoutError):
            await fake.cli(timeout=1.5).eval("return 1;", idempotent=True)
        assert len(fake.calls()) == 2

    async def test_other_calls_are_never_repeated_and_the_error_says_so(self, fake):
        fake.script(first_sleep="60", stdout=_envelope(ok=True, value="fine"))
        with pytest.raises(CLITimeoutError, match="check the vault before repeating a write"):
            await fake.cli(timeout=1.5).eval("return 1;")
        assert len(fake.calls()) == 1

    async def test_non_zero_exit_raises_cli_error(self, fake):
        fake.script(stderr="something broke", exit="3")
        with pytest.raises(
            ObsidianCLIError, match=r"obsidian eval failed \(exit 3\): something broke"
        ):
            await fake.cli().run("eval", "code=x")

    async def test_stderr_text_raises_even_with_exit_zero(self, fake):
        fake.script(stderr="warning: boom", stdout="=> data")
        with pytest.raises(ObsidianCLIError, match="warning: boom"):
            await fake.cli().run("eval", "code=x")

    async def test_cli_not_running_stderr_raises_obsidian_not_running(self, fake):
        fake.script(
            stderr="The CLI is unable to find Obsidian. Please make sure it is running.", exit="1"
        )
        with pytest.raises(ObsidianNotRunningError, match="Open the Obsidian desktop app"):
            await fake.cli().run("eval", "code=x")

    async def test_all_domain_errors_are_tool_errors(self):
        from mcp.server.mcpserver.exceptions import ToolError

        for error in (
            CLINotFoundError(),
            ObsidianNotRunningError(),
            CLITimeoutError(1, "eval"),
            ObsidianCLIError("x"),
            NoteNotFoundError("x"),
            NoteExistsError("x"),
            HeadingNotFoundError("x"),
            InvalidArgumentError("x"),
            ContentTooLargeError("x"),
        ):
            assert isinstance(error, ObsidianError) and isinstance(error, ToolError)


# ---------------------------------------------------------------------------
# Sentinels: the CLI reports failures as one line of stdout with exit 0
# ---------------------------------------------------------------------------

_DISABLED = (
    "Command line interface is not enabled. Please turn it on in Settings > General > Advanced."
)


class TestSentinels:
    async def test_cli_disabled(self, fake):
        fake.script(stdout=_DISABLED)
        with pytest.raises(
            ObsidianCLIError, match='Settings > General > Advanced > "Command line interface"'
        ):
            await fake.cli().run("eval", "code=x")

    async def test_vault_not_found(self, fake):
        fake.script(stdout="Vault not found.")
        with pytest.raises(ObsidianCLIError, match="Set OBSIDIAN_VAULT"):
            await fake.cli().run("eval", "code=x")

    @pytest.mark.parametrize(
        "line",
        [
            'Error: Command "eval" not found. Did you mean: events, evals?',
            'Error: Command "eval" not found. It may require a plugin to be enabled.',
        ],
    )
    async def test_command_not_found_for_the_invoked_command_raises_after_one_retry(
        self, fake, line
    ):
        fake.script(stdout=line)
        with pytest.raises(ObsidianCLIError, match="not found"):
            await fake.cli().run("eval", "code=x")
        assert len(fake.calls()) == 2

    async def test_cold_start_race_retries_once_and_succeeds(self, fake):
        fake.script(first_stdout='Error: Command "eval" not found.', stdout="=> fine")
        assert await fake.cli().run("eval", "code=x") == "=> fine"
        assert len(fake.calls()) == 2

    async def test_command_not_found_for_a_different_command_is_not_retried(self, fake):
        fake.script(stdout='Error: Command "other" not found.')
        with pytest.raises(ObsidianCLIError):  # the generic Error: rule still catches it
            await fake.cli().run("eval", "code=x")
        assert len(fake.calls()) == 1

    async def test_generic_error_line_raises(self, fake):
        fake.script(stdout="Error: Missing required parameter: query\nUsage: search:context ...")
        with pytest.raises(ObsidianCLIError, match="Missing required parameter"):
            await fake.cli().run("search:context", "format=json")

    async def test_sentinel_text_inside_a_bigger_result_is_data(self, fake):
        fake.script(stdout='[{"file":"a.md","matches":[{"line":1,"text":"Vault not found."}]}]')
        assert "Vault not found." in await fake.cli().run(
            "search:context", "query=x", "format=json"
        )

    @pytest.mark.parametrize(
        "preamble",
        [
            "2026-11-22 16:47:54 Loading main app package /Applications/Obsidian.app/x.asar\n",
            "2026-11-22 16:47:54 Loaded main app package /Applications/Obsidian.app/x.asar\n",
            "Your Obsidian installer is out of date. Please download the latest version.\n",
            "Ignored: Error: something\n",
        ],
    )
    async def test_app_launcher_preamble_is_a_wrong_binary_error(self, fake, preamble):
        fake.script(stdout=preamble + "=> data")
        with pytest.raises(ObsidianCLIError, match="set OBSIDIAN_CLI_PATH"):
            await fake.cli().run("eval", "code=x")


# ---------------------------------------------------------------------------
# eval envelope
# ---------------------------------------------------------------------------


def _envelope(**fields) -> str:
    return "=> " + json.dumps(fields)


def payload_of(argv: list[str]) -> Any:
    """The JSON payload inside one `eval` argv, whether it carries the snippet or only a call."""
    code = argv[2].removeprefix("code=")
    literal = code[code.index("window.__brain.run('") :].split("', ", 1)[1]
    return json.JSONDecoder().raw_decode(literal)[0]


class TestEval:
    async def test_returns_the_value(self, fake):
        fake.script(stdout=_envelope(ok=True, value={"a": [1, 2], "b": None}))
        assert await fake.cli().eval("return 1;") == {"a": [1, 2], "b": None}

    async def test_concurrent_cli_echo_lines_are_ignored(self, fake):
        """With parallel CLI processes Obsidian prints `Received CLI command [...]` first."""
        echo = 'Received CLI command ["eval","code=const input = {\\"content\\":\\"SECRET\\"}"]\n'
        fake.script(stdout=echo * 3 + _envelope(ok=True, value=7))
        assert await fake.cli().eval("return 7;") == 7
        fake.script(stdout=echo * 2 + "[1, 2]")
        assert await fake.cli().run("search:context", "query=x", "format=json") == "[1, 2]"

    async def test_echo_lines_never_leak_into_error_text(self, fake):
        echo = 'Received CLI command ["eval","code=SECRET-IN-ECHO"]\n'
        fake.script(stdout=echo + "garbage")
        with pytest.raises(ObsidianCLIError) as caught:
            await fake.cli().eval("return 1;")
        assert "SECRET-IN-ECHO" not in str(caught.value) and "garbage" in str(caught.value)

    async def test_missing_value_is_none(self, fake):
        fake.script(stdout=_envelope(ok=True))
        assert await fake.cli().eval("return;") is None

    async def test_the_first_call_installs_the_snippet_and_carries_the_payload(self, fake):
        """The payload is one JSON literal; \\n, \\t, BOM and LaTeX survive."""
        payload = {
            "text": 'a\\nb\\tc \\\\ $\\theta$ \r\n\ufeff日本語 😀 \u2028\u2029 \x00 "q" `t` ${x}',
            "n": 1,
        }
        fake.script(stdout=_envelope(ok=True, value=None))
        await fake.cli().eval("return input.n;", payload)
        (argv,) = fake.calls()
        code = argv[2].removeprefix("code=")
        assert "fns['" in code and "??= async (input) => {\nreturn input.n;\n};" in code
        assert payload_of(argv) == payload
        assert not set(code) & {"\ufeff", "\u2028", "\u2029"}  # escaped, not raw
        # One expression: `eval` runs a plain statement list as a script, where `return` is an error.
        assert code.startswith("(() => {") and code.endswith("})()")

    async def test_a_repeat_call_sends_only_the_payload(self, fake):
        """Obsidian logs every command's whole argv: a call stays short once the snippet is in."""
        fake.script(stdout=_envelope(ok=True, value=3))
        cli = fake.cli()
        body = "return input.n; // " + "padding " * 1000
        assert await cli.eval(body, {"n": 3}) == 3
        assert await cli.eval(body, {"n": 4}) == 3
        first, second = fake.calls()
        assert "padding" in first[2] and "padding" not in second[2]
        assert len(second[2]) < 300
        assert payload_of(second) == {"n": 4}
        await cli.eval("return 2;")  # another snippet is a first call again
        assert "async (input)" in fake.calls()[2][2]

    async def test_a_repeat_call_reports_errors_like_the_first(self, fake):
        cli = fake.cli()
        fake.script(stdout=_envelope(ok=True, value=1))
        await cli.eval("return 1;")
        fake.script(stdout=_envelope(ok=False, error={"code": "NOT_FOUND", "message": "gone"}))
        with pytest.raises(NoteNotFoundError, match="gone"):
            await cli.eval("return 1;")
        assert "async (input)" not in fake.calls()[1][2]  # it was the short call that failed

    async def test_a_window_that_lost_the_snippet_gets_it_again(self, fake):
        """A reloaded window (or one another server version took over) answers `missing`."""
        cli = fake.cli()
        fake.script(stdout=_envelope(ok=True, value="first"))
        assert await cli.eval("return 1;", {"n": 1}) == "first"
        fake.reset()
        fake.script(
            first_stdout=_envelope(ok=False, missing=True), stdout=_envelope(ok=True, value="again")
        )
        assert await cli.eval("return 1;", {"n": 2}) == "again"
        short, full = fake.calls()
        assert "async (input)" not in short[2] and "async (input)" in full[2]
        assert payload_of(short) == payload_of(full) == {"n": 2}
        fake.reset()
        fake.script(stdout=_envelope(ok=True, value="third"))
        assert await cli.eval("return 1;", {"n": 3}) == "third"
        assert "async (input)" not in fake.calls()[0][2]  # installed again: short call

    @pytest.mark.parametrize(
        ("code", "exception"),
        [
            ("NOT_FOUND", NoteNotFoundError),
            ("EXISTS", NoteExistsError),
            ("HEADING_NOT_FOUND", HeadingNotFoundError),
            ("INVALID", InvalidArgumentError),
            (None, ObsidianCLIError),
            ({"x": 1}, ObsidianCLIError),  # a thrown non-string code must not break the mapping
            ("SOMETHING_ELSE", ObsidianCLIError),
        ],
    )
    async def test_error_codes_map_to_exceptions(self, fake, code, exception):
        fake.script(stdout=_envelope(ok=False, error={"code": code, "message": "the message"}))
        with pytest.raises(exception, match="the message") as caught:
            await fake.cli().eval("throw 1;")
        assert type(caught.value) is exception

    @pytest.mark.parametrize(
        "stdout",
        [
            "",
            "just text",
            "Error: Illegal return statement",
            "=> not json",
            '=> {"nope": 1}',
            "=> [1]",
            "=> 7",
        ],
    )
    async def test_garbage_output_is_a_cli_error(self, fake, stdout):
        fake.script(stdout=stdout)
        with pytest.raises(ObsidianCLIError):
            await fake.cli().eval("return 1;")

    async def test_payload_over_the_ceiling_fails_before_spawning(self, fake):
        fake.script(stdout=_envelope(ok=True, value=1))
        with pytest.raises(ContentTooLargeError, match="at most 900 KB"):
            await fake.cli().eval("return 1;", {"content": "x" * MAX_PAYLOAD_BYTES})
        assert fake.calls() == []

    async def test_ceiling_counts_utf8_bytes_of_the_encoded_payload(self, fake):
        fake.script(stdout=_envelope(ok=True, value=1))
        # 300,000 three-byte characters: 900,000 bytes of content plus JSON quoting is over.
        with pytest.raises(ContentTooLargeError):
            await fake.cli().eval("return 1;", {"content": "日" * 300_000})
        # The same payload as 250,000 characters (750,000 bytes) is fine.
        assert await fake.cli().eval("return 1;", {"content": "日" * 250_000}) == 1

    async def test_payload_just_under_the_ceiling_is_sent(self, fake):
        fake.script(stdout=_envelope(ok=True, value=1))
        overhead = len(json.dumps({"content": ""}, separators=(",", ":")))
        assert (
            await fake.cli().eval("return 1;", {"content": "x" * (MAX_PAYLOAD_BYTES - overhead)})
            == 1
        )

    async def test_lone_surrogate_is_an_invalid_argument(self, fake):
        with pytest.raises(InvalidArgumentError, match="surrogate"):
            await fake.cli().eval("return 1;", {"content": "bad \ud800 text"})
        assert fake.calls() == []


class TestEvalsRunOneAtATime:
    """Obsidian's eval swaps console.log for each call and restores it out of order when calls
    overlap, leaving a swap behind that keeps every later console message (see MAX_EVALS_IN_FLIGHT)."""

    async def test_evals_wait_for_each_other(self, fake):
        fake.script(sleep="0.2", stdout=_envelope(ok=True, value=1))
        cli = fake.cli()
        await asyncio.gather(*(cli.eval(f"return {i};") for i in range(4)))
        assert len(fake.calls()) == 4 and fake.max_overlap() == 1

    async def test_the_bound_is_a_setting(self, fake):
        fake.script(sleep="0.3", stdout=_envelope(ok=True, value=1))
        cli = fake.cli(max_evals=2)
        await asyncio.gather(*(cli.eval(f"return {i};") for i in range(6)))
        assert fake.max_overlap() == 2

    async def test_waiting_for_a_turn_does_not_count_against_the_timeout(self, fake):
        fake.script(sleep="1", stdout=_envelope(ok=True, value=1))
        cli = fake.cli(timeout=1.5)  # the second call is answered 2 s after it was made
        assert await asyncio.gather(cli.eval("return 1;"), cli.eval("return 2;")) == [1, 1]

    async def test_commands_other_than_eval_do_not_wait_for_an_eval(self, fake):
        fake.script(first_sleep="1.5", stdout="[1]")
        cli = fake.cli()
        slow = asyncio.create_task(cli.run("eval", "code=1"))
        while not fake.calls():
            await asyncio.sleep(0.02)
        assert await cli.run("search:context", "query=x", "format=json") == "[1]"
        assert not slow.done()
        await slow

    async def test_a_lost_reply_is_repeated_before_the_next_eval_runs(self, fake):
        fake.script(first_sleep="60", stdout=_envelope(ok=True, value=1))
        cli = fake.cli(timeout=1.5)
        await asyncio.gather(cli.eval("return 'A';", idempotent=True), cli.eval("return 'B';"))
        assert ["'A'" in argv[2] for argv in fake.calls()] == [True, True, False]


class TestErrorsNeverContainThePayload:
    SECRET = "SECRET-NOTE-BODY-7f3a"

    @pytest.mark.parametrize(
        "script",
        [
            {"stderr": "boom", "exit": "1"},
            {"stdout": "garbage that is not an envelope"},
            {"stdout": _DISABLED},
            {"stdout": "Vault not found."},
            {"stdout": _envelope(ok=False, error={"code": None, "message": "js failed"})},
            {
                "stdout": _envelope(
                    ok=False, error={"code": "NOT_FOUND", "message": "Note not found: a.md"}
                )
            },
            {"sleep": "60"},
        ],
    )
    async def test_error_text_has_no_payload_or_argv_values(self, fake, script):
        fake.script(**script)
        with pytest.raises(ObsidianError) as caught:
            await fake.cli(timeout=1.5).eval("return input;", {"content": self.SECRET})
        assert self.SECRET not in str(caught.value)
        assert "code=" not in str(caught.value)
        assert self.SECRET in fake.calls()[0][2]  # the secret really was on the command line

    async def test_cli_output_in_errors_is_capped(self, fake):
        fake.script(stderr="x" * 5000, exit="1")
        with pytest.raises(ObsidianCLIError) as caught:
            await fake.cli().run("eval", "code=x")
        assert len(str(caught.value)) < 700


# ---------------------------------------------------------------------------
# Vault: arguments are validated in Python before anything is sent to Obsidian
# ---------------------------------------------------------------------------


def sent_input(fake: Any) -> dict[str, Any]:
    """The payload object of the one eval the fake CLI received."""
    (argv,) = fake.calls()
    parsed: dict[str, Any] = payload_of(argv)
    return parsed


class TestVaultValidation:
    @pytest.mark.parametrize(
        "path",
        ["", "/abs.md", "../x.md", "a/../b.md", "a/./b.md", "a//b.md", ".obsidian/x.md",
         "a\\b.md", "C:/x.md", "x\ny.md", "x\x00y.md", "folder/"],
    )  # fmt: skip
    async def test_bad_paths_never_reach_the_cli(self, fake, path):
        vault = Vault(fake.cli())
        for call in (
            vault.read_note(path),
            vault.write_note(path, "x"),
            vault.append(path, "x"),
            vault.delete(path),
            vault.update_tags(path, add=["a"]),
            vault.outgoing_links(path),
            vault.backlinks(path),
        ):
            with pytest.raises(InvalidArgumentError):
                await call
        assert fake.calls() == []

    async def test_bad_tags_never_reach_the_cli(self, fake):
        vault = Vault(fake.cli())
        for kwargs in (
            {"add": [""]},
            {"remove": ["a b"]},
            {"add": ["123"]},
            {},
            {"add": ["a"], "remove": ["#A"]},
        ):
            with pytest.raises(InvalidArgumentError):
                await vault.update_tags("n.md", **kwargs)
        with pytest.raises(InvalidArgumentError):
            await vault.notes_with_tag("a b")
        assert fake.calls() == []

    @pytest.mark.parametrize("query", ["\x00", "a\x00b", "a\nb", "tab\tx", "bell\x07", "   "])
    async def test_a_search_query_with_control_characters_is_refused_with_a_reason(
        self, fake, query
    ):
        with pytest.raises(InvalidArgumentError, match="query must not"):
            await Vault(fake.cli()).search(query)
        assert fake.calls() == []

    @pytest.mark.parametrize(
        ("path", "sent"),
        [
            ("Notes", "Notes.md"),
            ("Notes.md", "Notes.md"),
            ("Learning Node.js", "Learning Node.js.md"),
            ("Project.Alpha", "Project.Alpha.md"),
            ("J.R", "J.R.md"),
            ("data.json", "data.json.md"),
            ("UPPER.MD", "UPPER.MD"),
            ("Board.canvas", "Board.canvas"),
            ("scan.PDF", "scan.PDF"),
            ("a/b.png", "a/b.png"),
            ("Re\u0301sume\u0301", "R\u00e9sum\u00e9.md"),
        ],
    )
    async def test_md_is_added_unless_the_suffix_is_a_type_obsidian_opens(self, fake, path, sent):
        fake.script(stdout=_envelope(ok=True, value="ignored"))
        await Vault(fake.cli()).write_note(path, "x")
        assert sent_input(fake)["path"] == sent

    async def test_every_path_argument_is_sent_in_nfc(self, fake):
        nfd = "Fo\u0308lder/Re\u0301sume\u0301.md"
        nfc = unicodedata.normalize("NFC", nfd)
        assert nfd != nfc
        fake.script(stdout=_envelope(ok=True, value=None))
        vault = Vault(fake.cli())
        for call in (
            lambda: vault.delete(nfd),
            lambda: vault.append(nfd, "x"),
            lambda: vault.backlinks(nfd),
        ):
            fake.reset()
            fake.script(stdout=_envelope(ok=True, value=[]))
            await call()
            assert sent_input(fake)["path"] == nfc

    async def test_oversized_content_is_refused_before_spawning(self, fake):
        with pytest.raises(ContentTooLargeError):
            await Vault(fake.cli()).write_note("n.md", "x" * 1_048_577)
        assert fake.calls() == []

    async def test_only_repeatable_vault_calls_are_retried_after_a_lost_reply(self, fake):
        result = _envelope(ok=True, value={"tags": [], "added": [], "removed": []})
        for repeatable in (
            lambda v: v.resolve_link("a", "x.md"),
            lambda v: v.update_tags("a.md", add=["t"]),
            lambda v: v.write_note("a.md", "x", overwrite=True),
        ):
            fake.reset()
            fake.script(first_sleep="60", stdout=result)
            await repeatable(Vault(fake.cli(timeout=1.5)))
            assert len(fake.calls()) == 2
        for unsafe in (
            lambda v: v.append("a.md", "x"),
            lambda v: v.write_note("a.md", "x"),
            lambda v: v.delete("a.md"),
        ):
            fake.reset()
            fake.script(first_sleep="60", stdout=result)
            with pytest.raises(CLITimeoutError):
                await unsafe(Vault(fake.cli(timeout=1.5)))
            assert len(fake.calls()) == 1

    async def test_get_vault_is_one_process_wide_instance(self):
        assert get_vault() is get_vault() and isinstance(get_vault(), Vault)


class TestSearchSnippet:
    def test_short_lines_are_returned_whole(self):
        assert _snippet("a short line", "short") == "a short line"
        assert _snippet("x" * 300, "x") == "x" * 300

    def test_a_long_line_is_cut_around_the_first_query_word_found(self):
        text = "a" * 600 + " needle " + "b" * 600
        cut = _snippet(text, "missing needle")
        assert "needle" in cut and cut.startswith("…") and cut.endswith("…")
        assert len(cut) <= 302

    def test_operators_quotes_and_case_are_ignored_when_finding_the_match(self):
        text = "z" * 700 + " Exact Phrase " + "z" * 700
        for query in ('"exact phrase" path:Projects/ -skip', "tag:#x OR exact", "(EXACT)"):
            assert "Exact" in _snippet(text, query), query

    def test_a_match_at_the_start_or_the_end_gets_one_marker(self):
        start = _snippet("needle " + "b" * 900, "needle")
        assert start.startswith("needle") and start.endswith("…") and len(start) == 301
        end = _snippet("b" * 900 + " needle", "needle")
        assert end.startswith("…") and end.endswith("needle") and len(end) == 301

    def test_no_word_found_keeps_the_start_of_the_line(self):
        cut = _snippet("q" * 900, "absent")
        assert cut == "q" * 300 + "…"
