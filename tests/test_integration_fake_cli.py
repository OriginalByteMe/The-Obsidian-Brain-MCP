"""End-to-end MCP coverage using a deterministic fake Obsidian CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import dedent
from unittest.mock import AsyncMock
from typing import Any
from urllib.parse import quote

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, ReadResourceResult, TextContent, TextResourceContents
from pydantic import AnyUrl


def _install_fake_cli(tmp_path: Path) -> Path:
    executable = tmp_path / "obsidian"
    executable.write_text(
        f"#!{sys.executable}\n"
        + dedent(
            """\
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            vault_arg = next((arg for arg in args if arg.startswith("vault=")), None)
            if vault_arg is None:
                print("missing vault", file=sys.stderr)
                raise SystemExit(2)

            args.remove(vault_arg)
            root = Path(vault_arg.split("=", 1)[1]).resolve()
            command = args.pop(0)
            params = {}
            flags = set()
            for arg in args:
                if "=" in arg:
                    key, value = arg.split("=", 1)
                    params[key] = value
                else:
                    flags.add(arg)

            def target(raw_path):
                path = (root / raw_path).resolve()
                path.relative_to(root)
                return path

            def missing(path):
                print(f"ENOENT: no such file: {path}", file=sys.stderr)
                raise SystemExit(1)

            if command == "files":
                folder = params.get("folder", "").strip("/")
                prefix = f"{folder}/" if folder else ""
                extension = params.get("ext")
                paths = []
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(root).as_posix()
                    if prefix and not relative.startswith(prefix):
                        continue
                    if extension and path.suffix.lstrip(".") != extension.lstrip("."):
                        continue
                    paths.append(relative)
                print("\\n".join(sorted(paths)))
            elif command == "read":
                path = target(params["path"])
                if not path.is_file():
                    missing(params["path"])
                sys.stdout.write(path.read_text(encoding="utf-8"))
            elif command == "create":
                path = target(params["path"])
                if path.exists() and "overwrite" not in flags:
                    print(f"already exists: {params['path']}", file=sys.stderr)
                    raise SystemExit(1)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(params.get("content", ""), encoding="utf-8")
            elif command == "append":
                path = target(params["path"])
                if not path.is_file():
                    missing(params["path"])
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(params.get("content", ""))
            elif command == "delete":
                path = target(params["path"])
                if not path.is_file():
                    missing(params["path"])
                path.unlink()
            elif command == "search:context":
                query = params["query"]
                matches = []
                for path in sorted(root.rglob("*.md")):
                    relative = path.relative_to(root).as_posix()
                    for line_number, line in enumerate(
                        path.read_text(encoding="utf-8").splitlines(), start=1
                    ):
                        if query in line:
                            matches.append(f"{relative}:{line_number}: {line}")
                print("\\n".join(matches))
            else:
                print(f"unsupported command: {command}", file=sys.stderr)
                raise SystemExit(2)
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


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
