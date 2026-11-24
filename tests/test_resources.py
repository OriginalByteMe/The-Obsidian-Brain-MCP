"""Resources, read through an in-memory MCP client against `FakeVault` (no Obsidian needed)."""

import json
from typing import Any

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp_types import INVALID_PARAMS

from obsidian_brain import resources
from obsidian_brain.exceptions import ObsidianCLIError
from obsidian_brain.knowledge import KNOWLEDGE_BASE_PATH

from .conftest import read_resource
from .fake_vault import FakeVault

FILES = {
    "Home.md": "# Home\n\n[[Plan]] #index",
    "Projects/Alpha/Plan.md": "---\ntags: [project]\n---\n# Plan\n\n[[Home]]",
    "Odd #1 name.md": "x",
    "Attachments/diagram.png": "binary",
    "Obsidian Brain/config.md": "```yaml\na: 1\n```",
}


@pytest.fixture
def vault(monkeypatch: pytest.MonkeyPatch) -> FakeVault:
    fake = FakeVault(FILES)
    monkeypatch.setattr(resources, "get_vault", lambda: fake)
    return fake


@pytest.fixture
def server() -> MCPServer:
    app = MCPServer("test")
    resources.register(app)
    return app


async def test_resources_are_listed_with_json_mime_types(server: MCPServer) -> None:
    async with Client(server) as client:
        listed = {str(r.uri): r.mime_type for r in (await client.list_resources()).resources}
        templates = {
            t.uri_template: t.mime_type
            for t in (await client.list_resource_templates()).resource_templates
        }
    assert listed == {
        "vault://files": "application/json",
        "vault://tags": "application/json",
        "vault://stats": "application/json",
        "vault://knowledge": "text/markdown",
    }
    assert templates == {"vault://note/{+path}": "text/markdown"}


async def test_the_tags_resource_says_it_counts_occurrences_not_notes(server: MCPServer) -> None:
    async with Client(server) as client:
        tags = next(
            r for r in (await client.list_resources()).resources if str(r.uri) == "vault://tags"
        )
    description = (tags.description or "").lower()
    assert "occurrence" in description and "note count" not in description


async def test_files_lists_every_file_with_note_uris_for_markdown(
    server: MCPServer, vault: FakeVault
) -> None:
    text, mime = await read_resource(server, "vault://files")
    assert mime == "application/json"
    listing = json.loads(text)
    assert listing["total"] == len(FILES) == len(listing["files"])
    by_path = {f["path"]: f for f in listing["files"]}
    assert [f["path"] for f in listing["files"]] == sorted(FILES)
    assert by_path["Projects/Alpha/Plan.md"]["uri"] == "vault://note/Projects/Alpha/Plan.md"
    assert by_path["Odd #1 name.md"]["uri"] == "vault://note/Odd%20%231%20name.md"
    assert "uri" not in by_path["Attachments/diagram.png"]
    assert by_path["Home.md"]["modified"].endswith("Z")


@pytest.mark.parametrize(
    "uri",
    [
        "vault://note/Projects/Alpha/Plan.md",
        "vault://note/Projects%2FAlpha%2FPlan.md",
    ],
    ids=["unencoded-slash", "encoded-slash"],
)
async def test_note_resource_takes_slashes_encoded_or_not(
    server: MCPServer, vault: FakeVault, uri: str
) -> None:
    text, mime = await read_resource(server, uri)
    assert text == FILES["Projects/Alpha/Plan.md"] and mime == "text/markdown"


async def test_listed_note_uris_read_back(server: MCPServer, vault: FakeVault) -> None:
    listing = json.loads((await read_resource(server, "vault://files"))[0])
    for entry in listing["files"]:
        if "uri" in entry:
            assert (await read_resource(server, entry["uri"]))[0] == FILES[entry["path"]]


async def test_missing_note_is_not_found_without_cli_details(
    server: MCPServer, vault: FakeVault
) -> None:
    with pytest.raises(MCPError) as caught:
        await read_resource(server, "vault://note/Missing.md")
    assert caught.value.code == INVALID_PARAMS
    assert "Missing.md" in caught.value.message and "obsidian" not in caught.value.message.lower()


@pytest.mark.parametrize(
    "uri",
    ["vault://note/..%2Fetc%2Fpasswd", "vault://note/%2Fetc%2Fpasswd", "vault://note/a%00b.md"],
)
async def test_note_resource_refuses_traversal(
    server: MCPServer, vault: FakeVault, uri: str
) -> None:
    with pytest.raises(MCPError):
        await read_resource(server, uri)


async def test_vault_errors_become_resource_errors_not_bodies(
    server: MCPServer, vault: FakeVault, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise ObsidianCLIError("Obsidian's command line interface is disabled.")

    monkeypatch.setattr(vault, "snapshot", boom)
    monkeypatch.setattr(vault, "tags", boom)
    for uri in ("vault://stats", "vault://tags"):
        with pytest.raises(MCPError, match="command line interface is disabled"):
            await read_resource(server, uri)


async def test_tags_are_json_sorted_by_count(server: MCPServer, vault: FakeVault) -> None:
    text, mime = await read_resource(server, "vault://tags")
    assert mime == "application/json"
    assert json.loads(text) == {"index": 1, "project": 1}
    assert list(json.loads(text)) == ["index", "project"]


async def test_stats_are_json_and_leave_out_obsidian_brain(
    server: MCPServer, vault: FakeVault
) -> None:
    text, mime = await read_resource(server, "vault://stats")
    assert mime == "application/json"
    assert json.loads(text) == {
        "total_notes": 3,
        "total_folders": 3,  # Projects, Projects/Alpha, Attachments
        "total_tags": 2,
        "total_links": 2,
        "orphan_notes": 1,
    }


async def test_knowledge_resource_reads_the_file_or_says_how_to_make_it(
    server: MCPServer, vault: FakeVault
) -> None:
    with pytest.raises(MCPError, match="build_knowledge_base") as caught:
        await read_resource(server, "vault://knowledge")
    assert caught.value.code == INVALID_PARAMS
    vault.files[KNOWLEDGE_BASE_PATH] = "# Vault Knowledge Base\n"
    assert await read_resource(server, "vault://knowledge") == (
        "# Vault Knowledge Base\n",
        "text/markdown",
    )
