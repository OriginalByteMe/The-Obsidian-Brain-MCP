"""Memory, onboarding and knowledge base tools, driven through an in-memory MCP client.

They run against `FakeVault` (plain-text files, metadata parsed like Obsidian), so they need no
Obsidian. The live checks against a real vault are in test_live_higher.py.
"""

import itertools
from typing import Any

import pytest
import yaml
from mcp.server.mcpserver import MCPServer

from obsidian_brain.knowledge import KNOWLEDGE_BASE_PATH
from obsidian_brain.memory import MEMORIES_PATH, split_frontmatter
from obsidian_brain.onboarding import CONFIG_PATH, CONVENTIONS_PATH, OVERVIEW_PATH
from obsidian_brain.tools import knowledge as knowledge_tools
from obsidian_brain.tools import memory as memory_tools
from obsidian_brain.tools import onboarding as onboarding_tools

from .conftest import call, data, error_text, tool_list
from .fake_vault import FakeVault

MEMORY = f"{MEMORIES_PATH}/project-x.md"


@pytest.fixture
def vault(monkeypatch: pytest.MonkeyPatch) -> FakeVault:
    fake = FakeVault()
    for module in (memory_tools, onboarding_tools, knowledge_tools):
        monkeypatch.setattr(module, "get_vault", lambda fake=fake: fake)
    clock = (f"2026-11-23T03:00:{second:02d}Z" for second in itertools.count())
    for module in (memory_tools, knowledge_tools, onboarding_tools):
        monkeypatch.setattr(module, "utc_now", lambda clock=clock: next(clock))
    return fake


@pytest.fixture
def server() -> MCPServer:
    app = MCPServer("test")
    memory_tools.register(app)
    onboarding_tools.register(app)
    knowledge_tools.register(app)
    return app


def frontmatter(text: str) -> dict[str, Any]:
    block = split_frontmatter(text)[0]
    return yaml.safe_load("".join(block.splitlines(keepends=True)[1:-1])) or {}


# --- schema --------------------------------------------------------------------------------


async def test_name_constraints_are_in_the_schema(server: MCPServer) -> None:
    tools = await tool_list(server)
    name = tools["write_memory"].input_schema["properties"]["name"]
    assert (name["minLength"], name["maxLength"]) == (1, 200)
    assert tools["run_onboarding"].input_schema["properties"]["force"]["default"] is False


# --- memories ------------------------------------------------------------------------------


async def test_write_memory_creates_a_slugged_file_with_frontmatter(
    server: MCPServer, vault: FakeVault
) -> None:
    result = await call(
        server, "write_memory", name="Project X", content="Ship it", memory_type="project"
    )
    assert data(result) == {"name": "Project X", "path": MEMORY, "action": "created"}
    assert frontmatter(vault.files[MEMORY]) == {
        "name": "Project X",
        "type": "project",
        "created": "2026-11-23T03:00:00Z",
        "updated": "2026-11-23T03:00:00Z",
    }
    assert split_frontmatter(vault.files[MEMORY])[1] == "Ship it"


async def test_update_keeps_created_and_other_properties_and_honours_type(
    server: MCPServer, vault: FakeVault
) -> None:
    await call(server, "write_memory", name="Project X", content="v1", memory_type="project")
    vault.files[MEMORY] = vault.files[MEMORY].replace(
        "type: project", "type: project\ntags: [a, b]\ncustom: keep"
    )
    result = await call(
        server, "write_memory", name="Project X", content="v2", memory_type="decision"
    )
    assert data(result)["action"] == "updated"
    fm = frontmatter(vault.files[MEMORY])
    assert fm["created"] == "2026-11-23T03:00:00Z"
    assert fm["updated"] == "2026-11-23T03:00:01Z"
    assert (fm["type"], fm["custom"], fm["tags"]) == ("decision", "keep", ["a", "b"])
    assert split_frontmatter(vault.files[MEMORY])[1] == "v2"
    kept = await call(server, "write_memory", name="Project X", content="v3")
    assert not kept.is_error and frontmatter(vault.files[MEMORY])["type"] == "decision"


async def test_update_survives_dashes_inside_frontmatter_values(
    server: MCPServer, vault: FakeVault
) -> None:
    path = f"{MEMORIES_PATH}/dashval.md"
    vault.files[path] = '---\ntitle: "a --- b"\ntype: dash\n---\nbody of dashval'
    read = data(await call(server, "read_memory", name="dashval"))
    assert read["content"] == "body of dashval"
    assert read["frontmatter"] == {"title": "a --- b", "type": "dash"}
    await call(server, "write_memory", name="dashval", content="new body")
    fm = frontmatter(vault.files[path])
    assert (fm["title"], fm["type"], fm["name"]) == ("a --- b", "dash", "dashval")
    assert split_frontmatter(vault.files[path])[1] == "new body"


async def test_update_of_a_memory_without_frontmatter_adds_created(
    server: MCPServer, vault: FakeVault
) -> None:
    path = f"{MEMORIES_PATH}/nofm.md"
    vault.files[path] = "just text"
    await call(server, "write_memory", name="nofm", content="changed")
    fm = frontmatter(vault.files[path])
    assert fm["created"] == "2026-11-23T03:24:12Z"  # the file's modified time
    assert fm["updated"] == "2026-11-23T03:00:00Z"


async def test_an_update_edits_the_body_and_only_its_own_frontmatter_lines(
    server: MCPServer, vault: FakeVault
) -> None:
    """Numbers like 01234 and 1.10, empty values, flow lists and comments are not re-serialised."""
    path = f"{MEMORIES_PATH}/handmade.md"
    original = (
        "---\nname: handmade\ncode: 01234\nver: 1.10\nempty:\nlist: [a, b]\n# a comment\n"
        "type: old\ncreated: 2025-01-02T03:04:05Z\ntags:\n  - keep\n---\n\nold body\n"
    )
    vault.files[path] = original
    await call(server, "write_memory", name="handmade", content="new body", memory_type="note")
    expected = original.replace("type: old", "type: note").replace(
        "---\n\nold body\n", "updated: '2026-11-23T03:00:00Z'\n---\n\nnew body"
    )
    assert vault.files[path] == expected
    assert vault.calls[-1] == "replace_body" and "write_note" not in vault.calls  # one edit


async def test_update_fills_in_a_missing_name_and_created_only(
    server: MCPServer, vault: FakeVault
) -> None:
    path = f"{MEMORIES_PATH}/partial.md"
    vault.files[path] = "---\ncustom: 1\n---\nold"
    await call(server, "write_memory", name="partial", content="new")
    assert vault.files[path] == (
        "---\ncustom: 1\nname: partial\ncreated: '2026-11-23T03:24:12Z'\n"
        "updated: '2026-11-23T03:00:00Z'\n---\nnew"
    )


async def test_unparseable_frontmatter_is_never_dropped(
    server: MCPServer, vault: FakeVault
) -> None:
    path = f"{MEMORIES_PATH}/badyaml.md"
    original = "---\nfoo: [unclosed\n---\nbody"
    vault.files[path] = original
    result = await call(server, "write_memory", name="badyaml", content="new")
    assert "cannot parse" in error_text(result)
    assert vault.files[path] == original


async def test_read_memory_returns_tags_type_and_body(server: MCPServer, vault: FakeVault) -> None:
    vault.files[MEMORY] = (
        "---\nname: Project X\ntype: project\ntags: [alpha, beta]\n---\n\nDeadline #urgent"
    )
    read = data(await call(server, "read_memory", name="project x"))
    assert read["name"] == "Project X" and read["type"] == "project"
    assert read["content"] == "Deadline #urgent"
    assert read["tags"] == ["alpha", "beta", "urgent"]
    assert read["path"] == MEMORY


async def test_names_round_trip_through_list_read_and_delete(
    server: MCPServer, vault: FakeVault
) -> None:
    for path in ("Capital Name", "with space", "sub/deep"):
        vault.files[f"{MEMORIES_PATH}/{path}.md"] = f"body of {path}"
    listed = data(await call(server, "list_memories"))["memories"]
    names = [m["name"] for m in listed]
    assert names == ["Capital Name", "sub/deep", "with space"]
    for name in names:
        read = data(await call(server, "read_memory", name=name))
        assert read["content"] == f"body of {name}"
    deleted = data(await call(server, "delete_memory", name="CAPITAL name"))
    assert deleted["path"] == f"{MEMORIES_PATH}/Capital Name.md"
    assert vault.trashed == [f"{MEMORIES_PATH}/Capital Name.md"]


async def test_list_memories_is_one_vault_call(server: MCPServer, vault: FakeVault) -> None:
    for i in range(5):
        vault.files[f"{MEMORIES_PATH}/m{i}.md"] = f"---\ntype: t{i}\n---\nx"
    listed = data(await call(server, "list_memories"))
    assert listed["folder"] == MEMORIES_PATH
    assert [m["type"] for m in listed["memories"]] == [f"t{i}" for i in range(5)]
    assert vault.calls == ["snapshot"]


async def test_list_memories_without_a_memories_folder_is_empty(
    server: MCPServer, vault: FakeVault
) -> None:
    assert data(await call(server, "list_memories"))["memories"] == []


@pytest.mark.parametrize("name", ["..", "!!!", "   ", ".md", "💥", "/"])
async def test_names_without_letters_or_digits_write_nothing(
    server: MCPServer, vault: FakeVault, name: str
) -> None:
    result = await call(server, "write_memory", name=name, content="x")
    assert result.is_error and vault.writes == [] and vault.files == {}


async def test_a_second_spelling_of_the_same_slug_is_a_collision_not_an_overwrite(
    server: MCPServer, vault: FakeVault
) -> None:
    await call(server, "write_memory", name="Project X", content="first")
    before = vault.files[MEMORY]
    result = await call(server, "write_memory", name="project_x", content="intruder")
    assert "already uses the slug 'project-x'" in error_text(result)
    assert "'Project X'" in error_text(result)
    assert vault.files[MEMORY] == before
    read = data(await call(server, "read_memory", name="project_x"))  # reading is lenient
    assert read["content"] == "first"


async def test_a_file_in_the_way_of_a_new_slug_is_not_overwritten(
    server: MCPServer, vault: FakeVault
) -> None:
    vault.files[MEMORY] = "---\nname: Something else\n---\nmine"
    result = await call(server, "write_memory", name="Project X", content="theirs")
    assert result.is_error and vault.files[MEMORY].endswith("mine")


async def test_two_files_with_one_slug_are_reported_as_ambiguous(
    server: MCPServer, vault: FakeVault
) -> None:
    vault.files[f"{MEMORIES_PATH}/Foo Bar.md"] = "a"
    vault.files[f"{MEMORIES_PATH}/foo-bar.md"] = "b"
    for tool, args in (
        ("read_memory", {}),
        ("delete_memory", {}),
        ("write_memory", {"content": "c"}),
    ):
        assert "ambiguous" in error_text(await call(server, tool, name="foo bar", **args))
    assert vault.trashed == [] and vault.writes == []


async def test_nfd_and_nfc_spellings_are_one_memory(server: MCPServer, vault: FakeVault) -> None:
    await call(server, "write_memory", name="Cafe\u0301 notes", content="one")
    path = f"{MEMORIES_PATH}/caf\u00e9-notes.md"
    assert list(vault.files) == [path]
    again = await call(server, "write_memory", name="Caf\u00e9 notes", content="two")
    assert data(again)["action"] == "updated"


async def test_missing_memory_errors_name_the_memory_not_the_cli(
    server: MCPServer, vault: FakeVault
) -> None:
    for tool in ("read_memory", "delete_memory"):
        text = error_text(await call(server, tool, name="nope"))
        assert "No memory named 'nope'" in text and "list_memories" in text


async def test_overlong_name_is_a_clean_error(server: MCPServer, vault: FakeVault) -> None:
    result = await call(server, "write_memory", name="x" * 150 + "é" * 30, content="x")
    assert "too long" in error_text(result)


# --- onboarding ----------------------------------------------------------------------------

VAULT = {
    "Home.md": "---\nstatus: active\n---\n# Home\n\n[[Alpha]] #index",
    "1- Projects/Alpha.md": "# Alpha\n\n#project/alpha",
    "2 - Areas/Health.md": "# Health",
    "3 - Resources/Books.md": "# Books",
    "7 - Archives/Old.md": "# Old",
}


async def test_run_onboarding_writes_config_and_two_memories(
    server: MCPServer, vault: FakeVault
) -> None:
    vault.files.update(VAULT)
    result = data(await call(server, "run_onboarding"))
    assert result["created"] == [CONFIG_PATH, OVERVIEW_PATH, CONVENTIONS_PATH]
    assert result["overwritten"] == result["kept"] == []
    assert result["analysis"]["folder_patterns"] == ["PARA Method"]
    assert "```yaml" in vault.files[CONFIG_PATH]
    listed = data(await call(server, "list_memories"))["memories"]
    assert [m["name"] for m in listed] == ["conventions", "vault-overview"]


async def test_rerunning_onboarding_keeps_edited_files(server: MCPServer, vault: FakeVault) -> None:
    vault.files.update(VAULT)
    await call(server, "run_onboarding")
    vault.files[CONFIG_PATH] += "\ncustom_user_setting: keep-me   # USER EDIT\n"
    vault.files[OVERVIEW_PATH] += "\n## My own notes\nUSER EDIT\n"
    edited = {p: vault.files[p] for p in (CONFIG_PATH, OVERVIEW_PATH, CONVENTIONS_PATH)}

    result = data(await call(server, "run_onboarding"))

    assert result["kept"] == [CONFIG_PATH, OVERVIEW_PATH, CONVENTIONS_PATH]
    assert result["created"] == [] and result["overwritten"] == []
    assert {p: vault.files[p] for p in edited} == edited


async def test_force_regenerates_over_edits_and_says_so(
    server: MCPServer, vault: FakeVault
) -> None:
    vault.files.update(VAULT)
    await call(server, "run_onboarding")
    vault.files[CONFIG_PATH] += "USER EDIT"
    vault.files.pop(CONVENTIONS_PATH)
    result = data(await call(server, "run_onboarding", force=True))
    assert result["created"] == [CONVENTIONS_PATH]
    assert result["overwritten"] == [CONFIG_PATH, OVERVIEW_PATH]
    assert "USER EDIT" not in vault.files[CONFIG_PATH]


async def test_onboarding_analysis_ignores_its_own_files(
    server: MCPServer, vault: FakeVault
) -> None:
    vault.files.update(VAULT)
    first = data(await call(server, "run_onboarding"))["analysis"]
    second = data(await call(server, "run_onboarding", force=True))["analysis"]
    assert first == second


async def test_get_vault_config_before_onboarding(server: MCPServer, vault: FakeVault) -> None:
    config = data(await call(server, "get_vault_config"))
    assert config["onboarded"] is False and config["partial"] is False
    assert config["config"] is None and config["knowledge_base"]["exists"] is False
    assert "run_onboarding" in config["recommendation"]


async def test_get_vault_config_flags_a_half_finished_setup(
    server: MCPServer, vault: FakeVault
) -> None:
    vault.files[f"{MEMORIES_PATH}/stray.md"] = "x"
    config = data(await call(server, "get_vault_config"))
    assert (config["onboarded"], config["partial"], config["memories"]) == (False, True, 1)


async def test_get_vault_config_tolerates_text_before_the_fence(
    server: MCPServer, vault: FakeVault
) -> None:
    vault.files[CONFIG_PATH] = (
        "# My Config\n\nnotes above the fence\n\n```yaml\nversion: 1\n```\nnotes below"
    )
    config = data(await call(server, "get_vault_config"))
    assert config["onboarded"] is True and config["config"] == "version: 1"


async def test_get_vault_config_reports_the_knowledge_base(
    server: MCPServer, vault: FakeVault
) -> None:
    vault.files.update(VAULT)
    await call(server, "run_onboarding")
    assert "build_knowledge_base" in data(await call(server, "get_vault_config"))["recommendation"]
    await call(server, "build_knowledge_base")
    config = data(await call(server, "get_vault_config"))
    kb = config["knowledge_base"]
    assert kb["exists"] is True and kb["path"] == KNOWLEDGE_BASE_PATH
    assert kb["stats"]["total_notes"] == 5
    assert config["memories"] == 2


# --- knowledge base ------------------------------------------------------------------------


async def test_build_knowledge_base_keeps_created_and_ignores_itself(
    server: MCPServer, vault: FakeVault
) -> None:
    vault.files.update(VAULT)
    first = data(await call(server, "build_knowledge_base"))
    second = data(await call(server, "build_knowledge_base", include_orphans=False))
    assert (first["action"], second["action"]) == ("created", "updated")
    assert second["created"] == first["created"] != second["updated"]
    assert first["stats"] == second["stats"]
    assert first["stats"]["total_notes"] == 5 and first["stats"]["total_folders"] == 4
    fm = frontmatter(vault.files[KNOWLEDGE_BASE_PATH])
    assert fm["created"] == first["created"] and fm["updated"] == second["updated"]
    assert "## Orphan Notes" not in vault.files[KNOWLEDGE_BASE_PATH]
    assert "knowledge-base.md" not in vault.files[KNOWLEDGE_BASE_PATH].split("## Orphan")[0]
