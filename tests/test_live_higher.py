"""Memories, onboarding, the knowledge base and resources against a real Obsidian.

Only what the unit suites cannot show lives here: Obsidian's own metadata cache and parser,
real filenames, concurrency, and the real vault's structure. Everything else (slugs, collisions,
rendering, error text) is covered against `FakeVault` in test_tools_higher.py and test_resources.py.

Needs a running Obsidian with the CLI enabled and a disposable vault whose name contains
"testvault":

    OBSIDIAN_TEST_VAULT=obsidian-mcp-testvault-higher uv run pytest -m obsidian tests/test_live_higher.py

Each test drives the real server through an in-memory MCP client, and starts and ends with an
empty `Obsidian Brain/` folder (the only place these tools write).
"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import yaml
from mcp.shared.exceptions import MCPError
from mcp_types import INVALID_PARAMS

from obsidian_brain.exceptions import NoteNotFoundError
from obsidian_brain.knowledge import KNOWLEDGE_BASE_PATH
from obsidian_brain.memory import BRAIN_DIR, MEMORIES_PATH, split_frontmatter
from obsidian_brain.onboarding import CONFIG_PATH, CONVENTIONS_PATH, OVERVIEW_PATH
from obsidian_brain.server import server
from obsidian_brain.vault import Vault, get_vault

from .conftest import call, data, error_text, read_resource

pytestmark = pytest.mark.obsidian

MEMORY = f"{MEMORIES_PATH}/project-x.md"


async def _brain_files(vault: Vault) -> list[str]:
    try:
        return [f.path for f in await vault.list_files(BRAIN_DIR)]
    except NoteNotFoundError:
        return []


async def _clear(vault: Vault) -> None:
    for path in await _brain_files(vault):
        await vault.delete(path, permanent=True)


@pytest.fixture
async def vault(live_vault_name: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Vault]:
    """The vault the server's tools use (it reads OBSIDIAN_VAULT), emptied of `Obsidian Brain/`."""
    monkeypatch.setenv("OBSIDIAN_VAULT", live_vault_name)
    get_vault.cache_clear()  # the cached Vault was built for another OBSIDIAN_VAULT
    vault = get_vault()
    await _clear(vault)
    yield vault
    await _clear(vault)
    get_vault.cache_clear()


# --- memories ------------------------------------------------------------------------------


async def test_memory_lifecycle_keeps_text_verbatim_and_created_stable(vault: Vault) -> None:
    body = '$\\theta$ and print("a\\nb")\t---\n# Heading\n\nTrailing  \n'
    written = data(
        await call(server, "write_memory", name="Project X", content=body, memory_type="project")
    )
    assert written == {"name": "Project X", "path": MEMORY, "action": "created"}
    first = data(await call(server, "read_memory", name="project_x"))  # any spelling reads
    assert first["content"] == body and first["type"] == "project"
    assert split_frontmatter((await vault.read_note(MEMORY)).content)[1] == body

    text = (await vault.read_note(MEMORY)).content  # add a tag and a property by hand
    await vault.write_note(
        MEMORY, text.replace("---\n", "---\ntags:\n  - alpha\ncustom: keep\n", 1), overwrite=True
    )
    await asyncio.sleep(1.1)  # timestamps have second resolution
    updated = data(
        await call(
            server, "write_memory", name="Project X", content="v2 #inline", memory_type="decision"
        )
    )
    assert updated["action"] == "updated"
    second = data(await call(server, "read_memory", name="Project X"))
    assert second["content"] == "v2 #inline"
    assert (second["type"], second["created"]) == ("decision", first["created"])
    assert second["updated"] != first["updated"]
    assert second["frontmatter"]["custom"] == "keep"
    assert sorted(second["tags"]) == ["alpha", "inline"]

    await call(server, "write_memory", name="Project X", content="v3")  # no type given: kept
    assert data(await call(server, "read_memory", name="Project X"))["type"] == "decision"

    assert data(await call(server, "delete_memory", name="PROJECT-X"))["path"] == MEMORY
    assert await _brain_files(vault) == []
    assert "No memory named" in error_text(await call(server, "read_memory", name="Project X"))


async def test_nfd_and_nfc_spellings_are_one_memory(vault: Vault) -> None:
    await call(server, "write_memory", name="Cafe\u0301 notes", content="one")
    path = f"{MEMORIES_PATH}/caf\u00e9-notes.md"
    assert await _brain_files(vault) == [path]
    assert (
        data(await call(server, "write_memory", name="Caf\u00e9 notes", content="two"))["action"]
        == "updated"
    )
    names = [m["name"] for m in data(await call(server, "list_memories"))["memories"]]
    assert names == ["Caf\u00e9 notes"]


async def test_dashes_inside_frontmatter_values_survive_read_and_update(vault: Vault) -> None:
    path = f"{MEMORIES_PATH}/dashval.md"
    await vault.write_note(path, '---\ntitle: "a --- b"\ntype: dash\n---\nbody of dashval')
    read = data(await call(server, "read_memory", name="dashval"))
    assert read["content"] == "body of dashval"
    assert read["frontmatter"] == {"title": "a --- b", "type": "dash"}
    await call(server, "write_memory", name="dashval", content="new body")
    after = await vault.read_note(path)
    assert after.frontmatter["title"] == "a --- b" and after.frontmatter["type"] == "dash"
    assert split_frontmatter(after.content)[1] == "new body"


async def test_unparseable_frontmatter_is_not_overwritten(vault: Vault) -> None:
    path = f"{MEMORIES_PATH}/badyaml.md"
    original = "---\nfoo: [unclosed\n---\nbody"
    await vault.write_note(path, original)
    assert "cannot parse" in error_text(
        await call(server, "write_memory", name="badyaml", content="new")
    )
    assert (await vault.read_note(path)).content == original


async def test_parallel_writes_to_different_memories_all_land(vault: Vault) -> None:
    results = await asyncio.gather(
        *(call(server, "write_memory", name=f"parallel {i}", content=f"body {i}") for i in range(6))
    )
    assert [error_text(r) for r in results if r.is_error] == []
    names = sorted(m["name"] for m in data(await call(server, "list_memories"))["memories"])
    assert names == [f"parallel {i}" for i in range(6)]


# --- onboarding ----------------------------------------------------------------------------


async def test_onboarding_profiles_the_vault_and_a_rerun_keeps_manual_edits(vault: Vault) -> None:
    before = data(await call(server, "get_vault_config"))
    assert (before["onboarded"], before["partial"], before["config"]) == (False, False, None)

    first = data(await call(server, "run_onboarding"))
    assert first["created"] == [CONFIG_PATH, OVERVIEW_PATH, CONVENTIONS_PATH]
    assert first["overwritten"] == first["kept"] == []
    analysis = first["analysis"]
    assert "PARA Method" in analysis["folder_patterns"]  # Projects / Areas / Resources / Archive
    assert analysis["depth_levels"] >= 2
    assert analysis["folder_purposes"]["Daily"] == "Daily notes"
    assert analysis["folder_purposes"]["Templates"] == "Note templates"
    assert analysis["template_count"] >= 1

    config_text = (await vault.read_note(CONFIG_PATH)).content
    edited = config_text.replace("```\n", "custom_user_setting: keep-me   # USER EDIT\n```\n", 1)
    assert edited != config_text
    await vault.write_note(CONFIG_PATH, edited, overwrite=True)
    overview = (await vault.read_note(OVERVIEW_PATH)).content + "\n## My own notes\nUSER EDIT\n"
    await vault.write_note(OVERVIEW_PATH, overview, overwrite=True)

    again = data(await call(server, "run_onboarding"))
    assert again["kept"] == [CONFIG_PATH, OVERVIEW_PATH, CONVENTIONS_PATH]
    assert again["created"] == again["overwritten"] == []
    assert (await vault.read_note(CONFIG_PATH)).content == edited
    assert (await vault.read_note(OVERVIEW_PATH)).content == overview
    assert again["analysis"] == analysis  # its own files are not part of the analysis

    config = data(await call(server, "get_vault_config"))
    assert config["onboarded"] is True and config["memories"] == 2
    assert "custom_user_setting: keep-me" in config["config"]
    assert yaml.safe_load(config["config"])["custom_user_setting"] == "keep-me"

    forced = data(await call(server, "run_onboarding", force=True))
    assert forced["overwritten"] == [CONFIG_PATH, OVERVIEW_PATH, CONVENTIONS_PATH]
    assert "USER EDIT" not in (await vault.read_note(CONFIG_PATH)).content


# --- knowledge base ------------------------------------------------------------------------


async def test_knowledge_base_is_utc_keeps_created_and_ignores_its_own_files(vault: Vault) -> None:
    await call(server, "run_onboarding")
    first = data(await call(server, "build_knowledge_base"))
    assert first["action"] == "created"
    await asyncio.sleep(1.1)
    second = data(await call(server, "build_knowledge_base"))
    assert second["action"] == "updated"
    assert second["created"] == first["created"] != second["updated"]
    assert second["stats"] == first["stats"]

    text = (await vault.read_note(KNOWLEDGE_BASE_PATH)).content
    assert f"*Generated by Obsidian Brain MCP on {second['updated']}*" in text
    stamp = datetime.strptime(second["updated"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert abs((datetime.now(UTC) - stamp).total_seconds()) < 120
    assert "Obsidian Brain/" not in text.split("## Overview")[1]

    snapshot = await vault.snapshot()
    own = [f for f in snapshot.folders if f.startswith(BRAIN_DIR)]
    stats = second["stats"]
    assert stats["total_notes"] == len(
        [n for n in snapshot.notes if not n.path.startswith(BRAIN_DIR)]
    )
    assert stats["total_folders"] == len(snapshot.folders) - len(own)
    assert stats["total_folders"] > len([f for f in snapshot.folders if "/" not in f]) - len(
        [f for f in own if "/" not in f]
    )  # recursive, not just the root level

    status = data(await call(server, "get_vault_config"))["knowledge_base"]
    assert status["exists"] and status["created"] == first["created"]
    assert status["stats"] == stats


# --- resources -----------------------------------------------------------------------------


async def test_resources_return_json_and_raise_protocol_errors(vault: Vault) -> None:
    files_text, files_mime = await read_resource(server, "vault://files")
    listing = json.loads(files_text)
    assert files_mime == "application/json" and listing["total"] == len(listing["files"]) > 20

    tags_text, tags_mime = await read_resource(server, "vault://tags")
    tags = json.loads(tags_text)
    assert (
        tags_mime == "application/json" and tags and all(isinstance(n, int) for n in tags.values())
    )

    stats_text, stats_mime = await read_resource(server, "vault://stats")
    stats = json.loads(stats_text)
    assert stats_mime == "application/json"
    assert set(stats) == {
        "total_notes",
        "total_folders",
        "total_tags",
        "total_links",
        "orphan_notes",
    }

    with pytest.raises(MCPError, match="build_knowledge_base") as missing:
        await read_resource(server, "vault://knowledge")
    assert missing.value.code == INVALID_PARAMS
    await call(server, "build_knowledge_base")
    text, mime = await read_resource(server, "vault://knowledge")
    assert mime == "text/markdown" and text == (await vault.read_note(KNOWLEDGE_BASE_PATH)).content


async def test_note_resource_takes_unencoded_slashes_and_spaces(vault: Vault) -> None:
    path = "Projects/Alpha/Alpha Overview.md"
    expected = (await vault.read_note(path)).content
    listing = json.loads((await read_resource(server, "vault://files"))[0])
    uri = next(f["uri"] for f in listing["files"] if f["path"] == path)
    assert uri == "vault://note/Projects/Alpha/Alpha%20Overview.md"
    for variant in (uri, "vault://note/Projects%2FAlpha%2FAlpha%20Overview.md"):
        assert await read_resource(server, variant) == (expected, "text/markdown")
