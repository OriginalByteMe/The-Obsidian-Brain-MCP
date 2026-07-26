"""End-to-end MCP coverage using a deterministic fake Obsidian CLI.

Also includes focused contract tests for the fake binary itself, and an
opt-in end-to-end run against the real Obsidian CLI + a running Obsidian
app when one is available (see ``test_real_server_against_real_cli``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path
from textwrap import dedent
from typing import Any
from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, ReadResourceResult, TextContent, TextResourceContents
from pydantic import AnyUrl


def _install_fake_cli(tmp_path: Path) -> Path:
    """Write a fake ``obsidian`` executable mirroring obsidian-cli 1.12.7's contract.

    Verified against the real binary: it always exits 0 and reports failures
    as a single stdout line (``Error: ...`` / ``Vault not found.``), never
    stderr or a non-zero exit code. Successful mutations print a
    ``<Verb>: <path>`` line, and ``create`` on an existing path dedupes onto
    ``<stem> N.md`` instead of failing or overwriting.
    """
    executable = tmp_path / "obsidian"
    executable.write_text(
        f"#!{sys.executable}\n"
        + dedent(
            """\
            import sys
            from datetime import date
            from pathlib import Path

            args = sys.argv[1:]
            vault_arg = next((arg for arg in args if arg.startswith("vault=")), None)
            if vault_arg is None:
                print("Vault not found.")
                raise SystemExit(0)

            args.remove(vault_arg)
            root = Path(vault_arg.split("=", 1)[1]).expanduser().resolve()
            command = args.pop(0) if args else ""
            params = {}
            flags = set()
            for arg in args:
                if "=" in arg:
                    key, value = arg.split("=", 1)
                    params[key] = value
                else:
                    flags.add(arg)

            if not root.is_dir():
                print("Vault not found.")
                raise SystemExit(0)

            def target(raw_path):
                path = (root / raw_path).resolve()
                path.relative_to(root)
                return path

            def missing(raw_path):
                print(f'Error: File "{raw_path}" not found.')

            def dedupe_path(raw_path):
                path = target(raw_path)
                if not path.exists():
                    return raw_path, path
                stem, suffix = path.stem, path.suffix
                parent_raw = raw_path.rsplit("/", 1)[0] if "/" in raw_path else ""
                counter = 1
                while True:
                    name = f"{stem} {counter}{suffix}"
                    candidate = path.with_name(name)
                    if not candidate.exists():
                        return (f"{parent_raw}/{name}" if parent_raw else name), candidate
                    counter += 1

            if command == "files":
                folder = params.get("folder", "").strip("/")
                prefix = f"{folder}/" if folder else ""
                extension = params.get("ext")
                paths = []
                for entry in root.rglob("*"):
                    if not entry.is_file():
                        continue
                    relative = entry.relative_to(root).as_posix()
                    if prefix and not relative.startswith(prefix):
                        continue
                    if extension and entry.suffix.lstrip(".") != extension.lstrip("."):
                        continue
                    paths.append(relative)
                print("\\n".join(sorted(paths)))
            elif command == "read":
                raw_path = params["path"]
                path = target(raw_path)
                if path.is_file():
                    sys.stdout.write(path.read_text(encoding="utf-8"))
                else:
                    missing(raw_path)
            elif command == "create":
                raw_path = params["path"]
                if "overwrite" in flags:
                    path = target(raw_path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(params.get("content", ""), encoding="utf-8")
                    print(f"Overwrote: {raw_path}")
                else:
                    actual_raw, actual_path = dedupe_path(raw_path)
                    actual_path.parent.mkdir(parents=True, exist_ok=True)
                    actual_path.write_text(params.get("content", ""), encoding="utf-8")
                    print(f"Created: {actual_raw}")
            elif command == "append":
                raw_path = params["path"]
                path = target(raw_path)
                if path.is_file():
                    with path.open("a", encoding="utf-8") as handle:
                        handle.write(params.get("content", ""))
                    print(f"Appended to: {raw_path}")
                else:
                    missing(raw_path)
            elif command == "delete":
                raw_path = params["path"]
                path = target(raw_path)
                if path.is_file():
                    path.unlink()
                    print(f"Moved to trash: {raw_path}")
                else:
                    missing(raw_path)
            elif command == "search:context":
                query = params["query"]
                matches = []
                for entry in sorted(root.rglob("*.md")):
                    relative = entry.relative_to(root).as_posix()
                    for line_number, line in enumerate(
                        entry.read_text(encoding="utf-8").splitlines(), start=1
                    ):
                        if query in line:
                            matches.append(f"{relative}:{line_number}: {line}")
                print("\\n".join(matches) if matches else "No matches found.")
            elif command == "daily:path":
                day = params.get("date") or date.today().isoformat()
                print(f"{day}.md")
            elif command == "daily:read":
                day = params.get("date") or date.today().isoformat()
                path = root / f"{day}.md"
                if path.is_file():
                    sys.stdout.write(path.read_text(encoding="utf-8"))
            elif command == "daily:append":
                day = params.get("date") or date.today().isoformat()
                raw_path = f"{day}.md"
                path = root / raw_path
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(params.get("content", ""))
                print(f"Added to: {raw_path}")
            else:
                print(f'Error: Command "{command}" not found. It may require a plugin to be enabled.')
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _run_fake_cli(executable: Path, vault: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the fake ``obsidian`` binary directly, bypassing the MCP/client layers."""
    return subprocess.run(
        [str(executable), f"vault={vault}", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )


def _tool_json(result: CallToolResult) -> dict[str, Any]:
    assert not result.isError
    assert result.content
    content = result.content[0]
    assert isinstance(content, TextContent)
    parsed = json.loads(content.text)
    assert isinstance(parsed, dict)
    return parsed


def _resource_text(result: ReadResourceResult) -> str:
    content = result.contents[0]
    assert isinstance(content, TextResourceContents)
    return content.text


def _resource_json(result: ReadResourceResult) -> dict[str, Any]:
    parsed = json.loads(_resource_text(result))
    assert isinstance(parsed, dict)
    return parsed


def _note_uri(path: str) -> AnyUrl:
    return AnyUrl(f"vault://note/{quote(path, safe='')}")


def _frontmatter_block(text: str) -> str:
    """Return the leading ``---\\n...\\n---\\n`` frontmatter block, delimiters included."""
    lines = text.splitlines(keepends=True)
    assert lines[0].rstrip("\n") == "---", "expected a note starting with a frontmatter block"
    for index in range(1, len(lines)):
        if lines[index].rstrip("\n") == "---":
            return "".join(lines[: index + 1])
    raise AssertionError("frontmatter block was never closed")


# ---------------------------------------------------------------------------
# Direct contract tests: exercise the fake binary itself over a real
# subprocess, independent of the MCP/client stack. These pin down exactly
# the strings and exit codes verified against the real obsidian-cli 1.12.7.
# ---------------------------------------------------------------------------


def test_fake_cli_errors_are_stdout_lines_with_exit_zero(tmp_path: Path):
    """Every failure mode is rc=0 with the message on stdout, never stderr."""
    vault = tmp_path / "vault"
    vault.mkdir()
    executable = _install_fake_cli(tmp_path)

    for command, extra in [
        ("read", ("path=Nope.md",)),
        ("append", ("path=Nope.md", "content=x")),
        ("delete", ("path=Nope.md",)),
    ]:
        result = _run_fake_cli(executable, vault, command, *extra)
        assert result.returncode == 0
        assert result.stderr == ""
        assert result.stdout.strip() == 'Error: File "Nope.md" not found.'

    unresolvable = _run_fake_cli(executable, tmp_path / "no-such-vault", "files")
    assert unresolvable.returncode == 0
    assert unresolvable.stderr == ""
    assert unresolvable.stdout.strip() == "Vault not found."

    # A wholly missing vault= argument is just as "not found", never a hard failure.
    no_vault_arg = subprocess.run(
        [str(executable), "files"], capture_output=True, text=True, encoding="utf-8", timeout=10
    )
    assert no_vault_arg.returncode == 0
    assert no_vault_arg.stdout.strip() == "Vault not found."

    bogus = _run_fake_cli(executable, vault, "bogus:cmd")
    assert bogus.returncode == 0
    assert bogus.stderr == ""
    assert bogus.stdout.strip() == (
        'Error: Command "bogus:cmd" not found. It may require a plugin to be enabled.'
    )

    no_command = _run_fake_cli(executable, vault)
    assert no_command.returncode == 0
    assert no_command.stdout.strip() == (
        'Error: Command "" not found. It may require a plugin to be enabled.'
    )


def test_fake_cli_create_dedupes_then_overwrite_and_append_and_delete(tmp_path: Path):
    """create() dedupes an existing path; overwrite/append/delete report their verbs."""
    vault = tmp_path / "vault"
    (vault / "Projects").mkdir(parents=True)
    executable = _install_fake_cli(tmp_path)

    first = _run_fake_cli(executable, vault, "create", "path=Projects/Note.md", "content=one")
    assert first.stdout.strip() == "Created: Projects/Note.md"
    assert (vault / "Projects" / "Note.md").read_text(encoding="utf-8") == "one"

    duplicate = _run_fake_cli(executable, vault, "create", "path=Projects/Note.md", "content=two")
    assert duplicate.returncode == 0
    assert duplicate.stdout.strip() == "Created: Projects/Note 1.md"
    assert (vault / "Projects" / "Note.md").read_text(encoding="utf-8") == "one"
    assert (vault / "Projects" / "Note 1.md").read_text(encoding="utf-8") == "two"

    overwritten = _run_fake_cli(
        executable, vault, "create", "path=Projects/Note.md", "content=three", "overwrite"
    )
    assert overwritten.stdout.strip() == "Overwrote: Projects/Note.md"
    assert (vault / "Projects" / "Note.md").read_text(encoding="utf-8") == "three"
    assert (vault / "Projects" / "Note 1.md").read_text(encoding="utf-8") == "two"

    appended = _run_fake_cli(executable, vault, "append", "path=Projects/Note.md", "content=-more")
    assert appended.stdout.strip() == "Appended to: Projects/Note.md"
    assert (vault / "Projects" / "Note.md").read_text(encoding="utf-8") == "three-more"

    deleted = _run_fake_cli(executable, vault, "delete", "path=Projects/Note 1.md")
    assert deleted.stdout.strip() == "Moved to trash: Projects/Note 1.md"
    assert not (vault / "Projects" / "Note 1.md").exists()


def test_fake_cli_files_are_recursive_vault_relative_and_never_folders(tmp_path: Path):
    """files is always recursive, vault-relative, and lists only files."""
    vault = tmp_path / "vault"
    (vault / "Areas").mkdir(parents=True)
    (vault / "Areas" / "Log.md").write_text("log", encoding="utf-8")
    (vault / "Areas" / "diagram.png").write_bytes(b"\x89PNG")
    (vault / "Root.md").write_text("root", encoding="utf-8")
    executable = _install_fake_cli(tmp_path)

    everything = _run_fake_cli(executable, vault, "files")
    lines = everything.stdout.splitlines()
    assert set(lines) == {"Areas/Log.md", "Areas/diagram.png", "Root.md"}
    assert not any(line.endswith("/") for line in lines)

    scoped = _run_fake_cli(executable, vault, "files", "folder=Areas")
    assert set(scoped.stdout.splitlines()) == {"Areas/Log.md", "Areas/diagram.png"}

    filtered = _run_fake_cli(executable, vault, "files", "ext=md")
    assert set(filtered.stdout.splitlines()) == {"Areas/Log.md", "Root.md"}


def test_fake_cli_search_context_contract(tmp_path: Path):
    """search:context emits path:line: text, handles a colon in the filename,
    never matches inside a .canvas body, and reports empty matches distinctly."""
    vault = tmp_path / "vault"
    (vault / "Areas").mkdir(parents=True)
    (vault / "Areas" / "release:2026.md").write_text(
        "# Colon name\n\nneedle colon\n", encoding="utf-8"
    )
    (vault / "Board.canvas").write_text(
        json.dumps({"nodes": [{"id": "a", "type": "text", "text": "needle canvas"}]}),
        encoding="utf-8",
    )
    executable = _install_fake_cli(tmp_path)

    empty = _run_fake_cli(executable, vault, "search:context", "query=zzz-nothing", "format=text")
    assert empty.stdout.strip() == "No matches found."

    found = _run_fake_cli(executable, vault, "search:context", "query=needle", "format=text")
    assert found.stdout.splitlines() == ["Areas/release:2026.md:3: needle colon"]


def test_fake_cli_daily_commands_contract(tmp_path: Path):
    """daily:path always resolves a path; daily:read is silent when missing;
    daily:append creates the note and reports it."""
    vault = tmp_path / "vault"
    vault.mkdir()
    executable = _install_fake_cli(tmp_path)

    resolved_path = _run_fake_cli(executable, vault, "daily:path", "date=2030-01-01")
    assert resolved_path.stdout.strip() == "2030-01-01.md"

    default_path = _run_fake_cli(executable, vault, "daily:path")
    assert default_path.stdout.strip() == f"{date.today().isoformat()}.md"

    missing_read = _run_fake_cli(executable, vault, "daily:read", "date=2030-01-01")
    assert missing_read.returncode == 0
    assert missing_read.stdout == ""
    assert missing_read.stderr == ""

    added = _run_fake_cli(executable, vault, "daily:append", "content=- logged", "date=2030-01-01")
    assert added.stdout.strip() == "Added to: 2030-01-01.md"
    assert (vault / "2030-01-01.md").read_text(encoding="utf-8") == "- logged"

    now_readable = _run_fake_cli(executable, vault, "daily:read", "date=2030-01-01")
    assert now_readable.stdout == "- logged"


# ---------------------------------------------------------------------------
# Full stack: MCP tools/resources -> ObsidianCLIClient -> the fake binary.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_server_against_fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vault = tmp_path / "vault"
    nested = vault / "Projects" / "Same.md"
    root_sibling = vault / "Same.md"
    nested.parent.mkdir(parents=True)
    root_sibling.write_text("# Root sibling\n\nneedle root\n", encoding="utf-8")
    nested.write_text("# Nested original\n", encoding="utf-8")
    (vault / "Assets").mkdir()
    (vault / "Assets" / "cover.png").write_bytes(b"\x89PNG\r\n")
    (vault / "Board.canvas").write_text("{}", encoding="utf-8")
    (vault / "config.yml").write_text("enabled: true\n", encoding="utf-8")

    executable = _install_fake_cli(tmp_path)
    monkeypatch.setenv("OBSIDIAN_CLI_PATH", str(executable))
    monkeypatch.setenv("OBSIDIAN_VAULT", str(vault))

    import obsidian_brain.cli_client as cli_module
    from obsidian_brain.cache import vault_cache
    from obsidian_brain.server import client, mcp

    monkeypatch.setattr(cli_module, "_check_obsidian_running", AsyncMock())
    monkeypatch.setattr(client, "cli_path", None)
    monkeypatch.setattr(client, "vault", str(vault))
    monkeypatch.setattr(vault_cache, "_structure", None)
    monkeypatch.setattr(vault_cache, "_file_paths", [], raising=False)
    monkeypatch.setattr(vault_cache, "_backlink_index", {})

    async with create_connected_server_and_client_session(mcp) as session:
        refreshed = _tool_json(await session.call_tool("refresh_vault_structure", {}))
        assert refreshed["success"] is True

        index = _resource_json(await session.read_resource(AnyUrl("vault://files")))
        files = {entry["path"]: entry for entry in index["files"]}
        assert files["Assets/cover.png"] == {
            "path": "Assets/cover.png",
            "extension": ".png",
            "readable": False,
        }
        assert files["Board.canvas"]["readable"] is False
        assert files["config.yml"]["extension"] == ".yml"
        assert files["Projects/Same.md"]["uri"] == "vault://note/Projects%2FSame.md"

        body = (
            "# Nested\n\n"
            "```md\n## Notes\nfenced decoy\n```\n\n"
            "## Notes\nExisting\n\nneedle nested\n"
        )
        replacement = f"---\ntags:\n  - project\naliases:\n  - Nested\n---\n{body}"
        updated = _tool_json(
            await session.call_tool(
                "update_note", {"path": "Projects/Same.md", "content": replacement}
            )
        )
        assert updated["success"] is True
        assert root_sibling.read_text(encoding="utf-8") == "# Root sibling\n\nneedle root\n"
        assert nested.read_text(encoding="utf-8") == replacement
        after_update = await session.read_resource(_note_uri("Projects/Same.md"))
        # The resource serves the file as-is, frontmatter included.
        assert _resource_text(after_update) == replacement

        appended = _tool_json(
            await session.call_tool(
                "append_to_note",
                {
                    "path": "Projects/Same.md",
                    "content": "inserted under real heading",
                    "heading": "## Notes",
                },
            )
        )
        assert appended["success"] is True
        edited = nested.read_text(encoding="utf-8")
        expected_edit = replacement.replace(
            "## Notes\nExisting",
            "## Notes\ninserted under real heading\nExisting",
        )
        assert edited == expected_edit
        assert root_sibling.read_text(encoding="utf-8") == "# Root sibling\n\nneedle root\n"
        after_append = await session.read_resource(_note_uri("Projects/Same.md"))
        assert _resource_text(after_append) == expected_edit
        listed_tags = _tool_json(await session.call_tool("list_all_tags", {}))
        assert listed_tags == {
            "success": True,
            "tags": {"project": 1},
            "total_unique_tags": 1,
            "total_tag_usage": 1,
        }

        created = _tool_json(
            await session.call_tool(
                "create_note",
                {"path": "Projects/Created.md", "content": "needle created"},
            )
        )
        assert created["success"] is True
        index_after_edits = _resource_json(await session.read_resource(AnyUrl("vault://files")))
        paths_after_edits = {entry["path"] for entry in index_after_edits["files"]}
        assert {"Projects/Same.md", "Projects/Created.md"} <= paths_after_edits
        created_resource = await session.read_resource(_note_uri("Projects/Created.md"))
        assert "needle created" in _resource_text(created_resource)

        # Obsidian dedupes create() on an existing path instead of failing or
        # clobbering it; the tool surfaces the actual path so callers can tell.
        duplicate_path = "Projects/Created.md"
        expected_dedupe_path = "Projects/Created 1.md"
        original_created_text = (vault / "Projects" / "Created.md").read_text(encoding="utf-8")
        duplicate = _tool_json(
            await session.call_tool(
                "create_note",
                {"path": duplicate_path, "content": "second create attempt"},
            )
        )
        assert duplicate["success"] is True
        assert duplicate["path"] == expected_dedupe_path
        assert duplicate_path in duplicate["message"]
        assert expected_dedupe_path in duplicate["message"]
        assert (vault / "Projects" / "Created.md").read_text(
            encoding="utf-8"
        ) == original_created_text
        assert "second create attempt" in (vault / "Projects" / "Created 1.md").read_text(
            encoding="utf-8"
        )
        deduped_resource = await session.read_resource(_note_uri(expected_dedupe_path))
        assert "second create attempt" in _resource_text(deduped_resource)

        search = _tool_json(await session.call_tool("search_content", {"query": "needle"}))
        matches = {item["path"]: item["matches"] for item in search["results"]}
        assert matches == {
            "Projects/Created.md": ["needle created"],
            "Projects/Same.md": ["needle nested"],
            "Same.md": ["needle root"],
        }
        assert search["total_matches"] == 3

        missing = _tool_json(await session.call_tool("get_note", {"path": "Missing.md"}))
        assert missing == {
            "error": True,
            "type": "NoteNotFoundError",
            "message": "Note not found: Missing.md",
        }


# ---------------------------------------------------------------------------
# Opt-in: the same MCP session driven against the real obsidian-cli and a
# running Obsidian app, guarded to only ever touch a disposable test vault.
# ---------------------------------------------------------------------------


def _find_real_cli_binary() -> str | None:
    """Resolve a real obsidian-cli-style binary path, or None if unavailable."""
    env_path = os.environ.get("OBSIDIAN_CLI_PATH")
    if env_path:
        return env_path if os.path.isfile(env_path) and os.access(env_path, os.X_OK) else None
    default = os.path.expanduser("~/Applications/obsidian-cli")
    return default if os.path.isfile(default) and os.access(default, os.X_OK) else None


def _real_cli_socket_path() -> Path | None:
    """Return the CLI's IPC socket path if it exists, else None."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir:
        return None
    sock = Path(runtime_dir) / ".obsidian-cli.sock"
    return sock if sock.exists() else None


def _resolve_real_vault_path(vault_name: str) -> Path | None:
    """Resolve OBSIDIAN_VAULT to the absolute directory obsidian-cli would use.

    Empirically, the real CLI's own ``vault=`` argument only understands a
    registered vault id or folder basename -- a raw filesystem path is
    rejected with "Vault not found." -- so this never trusts the raw value
    directly and always looks it up the same way: by exact vault id or
    folder basename in Obsidian's own registry
    (``~/.config/obsidian/obsidian.json``). A missing or ambiguous match
    returns None so callers fail closed instead of guessing.
    """
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser()
    try:
        registry = json.loads(
            (config_home / "obsidian" / "obsidian.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None

    vaults = registry.get("vaults")
    if not isinstance(vaults, dict):
        return None

    matches = {
        Path(info["path"]).resolve()
        for vault_id, info in vaults.items()
        if isinstance(info, dict)
        and isinstance(info.get("path"), str)
        and (vault_id == vault_name or Path(info["path"]).name == vault_name)
    }
    return matches.pop() if len(matches) == 1 else None


_DISPOSABLE_SENTINEL = ".obsidian-mcp-disposable"


def _real_cli_skip_reason() -> str | None:
    """Return why the opt-in real-CLI test must skip, or None when it can run.

    This test WRITES to a vault, so the gate fails closed on two explicit
    signals rather than on a guessable path substring: the operator must set
    OBSIDIAN_MCP_ALLOW_REAL_VAULT_WRITES=1, and the resolved vault must
    contain a `.obsidian-mcp-disposable` marker file created by whoever built
    that throwaway vault. A real vault has neither.
    """
    if os.environ.get("OBSIDIAN_MCP_ALLOW_REAL_VAULT_WRITES") != "1":
        return "OBSIDIAN_MCP_ALLOW_REAL_VAULT_WRITES=1 is not set (this test writes to a vault)"

    if _find_real_cli_binary() is None:
        return "no obsidian-cli binary at $OBSIDIAN_CLI_PATH or ~/Applications/obsidian-cli"

    if _real_cli_socket_path() is None:
        return 'no "$XDG_RUNTIME_DIR/.obsidian-cli.sock" (Obsidian CLI not enabled/running)'

    vault_name = os.environ.get("OBSIDIAN_VAULT")
    if not vault_name:
        return "OBSIDIAN_VAULT is not set"

    vault_path = _resolve_real_vault_path(vault_name)
    if vault_path is None or not vault_path.is_dir():
        return f"OBSIDIAN_VAULT={vault_name!r} does not resolve to exactly one real vault directory"

    if not (vault_path / _DISPOSABLE_SENTINEL).is_file():
        return (
            f"resolved vault {vault_path} has no {_DISPOSABLE_SENTINEL} marker file, "
            "so it is not a declared disposable vault"
        )

    return None


# Computed once at collection time for the skipif decorator below.
_REAL_CLI_SKIP_REASON = _real_cli_skip_reason()


@pytest.mark.real_cli
@pytest.mark.skipif(
    _REAL_CLI_SKIP_REASON is not None,
    reason=_REAL_CLI_SKIP_REASON or "real Obsidian CLI available",
)
@pytest.mark.asyncio
async def test_real_server_against_real_cli(monkeypatch: pytest.MonkeyPatch):
    """Opt-in end-to-end run against the real obsidian-cli and a running Obsidian app.

    Only runs when the operator has explicitly allowed vault writes, the real
    CLI and its IPC socket are present, and OBSIDIAN_VAULT resolves through
    Obsidian's own registry to a directory carrying the
    ``.obsidian-mcp-disposable`` marker -- see ``_real_cli_skip_reason``. The
    env var is never trusted as a safety signal by itself, so a misconfigured
    value can only make this skip, never mutate a real vault.
    """
    binary = _find_real_cli_binary()
    vault_name = os.environ["OBSIDIAN_VAULT"]
    vault_path = _resolve_real_vault_path(vault_name)
    assert binary is not None
    assert vault_path is not None
    assert (vault_path / _DISPOSABLE_SENTINEL).is_file()

    import obsidian_brain.cli_client as cli_module
    from obsidian_brain.cache import vault_cache
    from obsidian_brain.server import client, mcp

    # The socket's presence already proves a live instance is listening; skip
    # the pgrep-based heuristic so an environment-specific process-name
    # mismatch can't make this opt-in test flaky.
    monkeypatch.setattr(cli_module, "_check_obsidian_running", AsyncMock())
    monkeypatch.setattr(client, "cli_path", binary)
    monkeypatch.setattr(client, "vault", vault_name)
    monkeypatch.setattr(vault_cache, "_structure", None)
    monkeypatch.setattr(vault_cache, "_file_paths", [], raising=False)
    monkeypatch.setattr(vault_cache, "_backlink_index", {})

    # Two disposable notes share a basename in different folders, so an edit
    # aimed at one can be proven to never land on the other.
    marker = uuid.uuid4().hex
    basename = f"RealCliProbe-{marker}.md"
    target_rel = f"Areas/{basename}"
    sibling_rel = f"Projects/{basename}"

    async with create_connected_server_and_client_session(mcp) as session:
        try:
            refreshed = _tool_json(await session.call_tool("refresh_vault_structure", {}))
            assert refreshed["success"] is True

            # vault://files includes a non-Markdown file.
            index = _resource_json(await session.read_resource(AnyUrl("vault://files")))
            paths = {entry["path"] for entry in index["files"]}
            assert any(not path.lower().endswith(".md") for path in paths)

            created_target = _tool_json(
                await session.call_tool(
                    "create_note",
                    {"path": target_rel, "content": f"needle {marker} target"},
                )
            )
            assert created_target["success"] is True
            assert created_target["path"] == target_rel
            target_file = vault_path / created_target["path"]
            frontmatter_before = _frontmatter_block(target_file.read_text(encoding="utf-8"))

            created_sibling = _tool_json(
                await session.call_tool(
                    "create_note",
                    {"path": sibling_rel, "content": f"needle {marker} sibling"},
                )
            )
            assert created_sibling["success"] is True
            assert created_sibling["path"] == sibling_rel
            sibling_file = vault_path / created_sibling["path"]
            sibling_before = sibling_file.read_text(encoding="utf-8")

            # A nested edit hits the exact path; frontmatter survives a headed append.
            appended = _tool_json(
                await session.call_tool(
                    "append_to_note",
                    {
                        "path": target_rel,
                        "content": "appended under heading",
                        "heading": "## Log",
                    },
                )
            )
            assert appended["success"] is True
            after_append = target_file.read_text(encoding="utf-8")
            assert _frontmatter_block(after_append) == frontmatter_before
            assert f"needle {marker} target" in after_append
            assert "appended under heading" in after_append

            # The same-basename sibling in a different folder is untouched.
            assert sibling_file.read_text(encoding="utf-8") == sibling_before

            # Search returns per-file context, not a bare path list.
            search = _tool_json(await session.call_tool("search_content", {"query": marker}))
            matches = {item["path"]: item["matches"] for item in search["results"]}
            assert target_rel in matches
            assert sibling_rel in matches
            assert any(marker in line for line in matches[target_rel])
            assert any(marker in line for line in matches[sibling_rel])

            # A missing note yields the documented NoteNotFoundError JSON.
            missing_path = f"Nope-{marker}.md"
            missing = _tool_json(await session.call_tool("get_note", {"path": missing_path}))
            assert missing == {
                "error": True,
                "type": "NoteNotFoundError",
                "message": f"Note not found: {missing_path}",
            }
            # Remove the probes the same way a client would, so Obsidian's own
            # index stays consistent; the unlink below is only a safety net.
            for rel in (target_rel, sibling_rel):
                deleted = _tool_json(await session.call_tool("delete_note", {"path": rel}))
                assert deleted["success"] is True, deleted
                assert not (vault_path / rel).exists()
        finally:
            (vault_path / target_rel).unlink(missing_ok=True)
            (vault_path / sibling_rel).unlink(missing_ok=True)
