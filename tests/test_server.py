"""The assembled server: tool and resource surface, instructions, version, import hygiene."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

from mcp import Client
from mcp.server.mcpserver import MCPServer

from obsidian_brain import __version__
from obsidian_brain.server import INSTRUCTIONS, server

from .conftest import tool_list

ROOT = Path(__file__).parent.parent

# Every tool and what it does to the vault: it only reads, adds to it without destroying
# anything, or can lose existing content (replace, delete, regenerate).
EFFECTS = {
    "list_vault_files": "read",
    "get_note": "read",
    "write_note": "destructive",
    "append_to_note": "additive",
    "delete_note": "destructive",
    "update_tags": "additive",
    "list_all_tags": "read",
    "get_notes_by_tag": "read",
    "get_links": "read",
    "add_link": "additive",
    "search_content": "read",
    "get_daily_note": "read",
    "append_to_daily": "additive",
    "list_memories": "read",
    "read_memory": "read",
    "write_memory": "destructive",
    "delete_memory": "destructive",
    "get_vault_config": "read",
    "run_onboarding": "destructive",
    "build_knowledge_base": "destructive",
}
TOOLS = set(EFFECTS)
IDEMPOTENT = {"update_tags", "add_link"}  # running them twice leaves the same vault


def test_server_identity() -> None:
    assert isinstance(server, MCPServer)
    assert server.name == "obsidian-brain"
    assert server.version == __version__ == _pyproject_version()


def _pyproject_version() -> str:
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    return tomllib.loads(pyproject.read_text())["project"]["version"]  # type: ignore[no-any-return]


def test_instructions_are_short_and_state_prerequisites_not_tools() -> None:
    assert len(INSTRUCTIONS.strip().splitlines()) <= 20
    assert "get_vault_config" in INSTRUCTIONS
    for prerequisite in ("Obsidian is open", "Command line interface", "OBSIDIAN_VAULT"):
        assert prerequisite in INSTRUCTIONS
    for tool in TOOLS - {"get_vault_config"}:
        assert tool not in INSTRUCTIONS, f"{tool} listed in instructions"


async def test_every_tool_is_annotated_and_documented() -> None:
    """The only per-tool surface check: all 20 tools, one table."""
    tools = await tool_list(server)
    assert set(tools) == TOOLS
    for name, tool in tools.items():
        effect = EFFECTS[name]
        hints = tool.annotations
        assert hints is not None and hints.open_world_hint is False, name
        assert hints.read_only_hint is (effect == "read"), name
        if effect != "read":
            assert hints.destructive_hint is (effect == "destructive"), name
        assert (hints.idempotent_hint is True) == (name in IDEMPOTENT), name
        assert tool.output_schema, f"{name} returns no structured output"
        description = tool.description or ""
        assert len(description.splitlines()) >= 3, name  # purpose, siblings, example
        assert f"Example: {name}(" in description, f"{name} has no example call"
        assert any(other in description for other in TOOLS - {name}), f"{name} names no sibling"
        for param, schema in tool.input_schema.get("properties", {}).items():
            assert schema.get("description"), f"{name}.{param} has no description"


def test_the_docs_list_every_registered_tool_and_the_version() -> None:
    for doc in ("README.md", "SPECIFICATION.md"):
        text = (ROOT / doc).read_text()
        assert [t for t in sorted(TOOLS) if f"`{t}" not in text] == [], doc
        assert "mcp>=2.3" in text, doc
    assert f"**Version**: {__version__}" in (ROOT / "SPECIFICATION.md").read_text()


async def test_resources_and_note_template_are_registered() -> None:
    async with Client(server) as client:
        resources = {str(r.uri): r.mime_type for r in (await client.list_resources()).resources}
        templates = (await client.list_resource_templates()).resource_templates
    assert resources == {
        "vault://files": "application/json",
        "vault://tags": "application/json",
        "vault://stats": "application/json",
        "vault://knowledge": "text/markdown",
    }
    assert [(t.uri_template, t.mime_type) for t in templates] == [
        ("vault://note/{+path}", "text/markdown")
    ]


def test_importing_the_server_needs_no_obsidian() -> None:
    env = {k: v for k, v in os.environ.items() if k != "OBSIDIAN_CLI_PATH"} | {"PATH": ""}
    result = subprocess.run(
        [sys.executable, "-c", "import obsidian_brain.server"],
        capture_output=True,
        env=env,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
