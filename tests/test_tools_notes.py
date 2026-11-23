"""Tests for the note, link, tag and search tools.

The plain tests drive the tools through an in-memory MCP client against the in-memory
`FakeVault` (tests/fake_vault.py), so they need no Obsidian. The `obsidian` tests at the bottom
run the real tools against the disposable vault named by OBSIDIAN_TEST_VAULT
(`pytest -m obsidian`); they check the wiring, the Vault-level live suite checks the behaviour.
"""

from __future__ import annotations

import unicodedata
import uuid
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from obsidian_brain.models import SearchHit, SearchMatch, SearchResults
from obsidian_brain.obsidian import ObsidianCLI
from obsidian_brain.server import server as real_server
from obsidian_brain.tools import notes
from obsidian_brain.vault import Vault

from .conftest import (
    Sandbox,
    call,
    data,
    error_text,
    eventually,
    live_tools,
    tool_list,
)
from .fake_vault import FakeVault

NFD = "Re\u0301sume\u0301.md"
NFC = unicodedata.normalize("NFC", NFD)

# --- schemas -------------------------------------------------------------------------------


async def test_constraints_are_visible_in_schemas(note_tools: MCPServer) -> None:
    tools = await tool_list(note_tools)
    links = tools["get_links"].input_schema["properties"]
    assert links["direction"]["enum"] == ["outgoing", "incoming", "both"]
    assert (links["depth"]["minimum"], links["depth"]["maximum"]) == (1, 3)
    search = tools["search_content"].input_schema["properties"]
    assert search["query"]["minLength"] == 1
    assert (search["limit"]["minimum"], search["limit"]["maximum"]) == (1, 100)
    assert tools["list_vault_files"].input_schema["properties"]["offset"]["minimum"] == 0
    add = tools["update_tags"].input_schema["properties"]["add"]
    assert any(branch.get("items", {}).get("pattern") for branch in add["anyOf"])
    assert tools["append_to_note"].input_schema["properties"]["content"]["minLength"] == 1
    date_schema = tools["get_daily_note"].input_schema["properties"]["date"]
    assert any(branch.get("pattern") == r"^\d{4}-\d{2}-\d{2}$" for branch in date_schema["anyOf"])
    description = tools["search_content"].description or ""
    for syntax in ("path:", "tag:", "ALL of them", "exact phrase"):
        assert syntax in description


async def test_tag_counts_are_named_and_described_as_occurrences(note_tools: MCPServer) -> None:
    tools = await tool_list(note_tools)
    output = tools["list_all_tags"].output_schema
    assert output is not None
    count = output["$defs"]["TagCount"]["properties"]
    assert set(count) == {"tag", "occurrences"}
    assert "not a number of notes" in count["occurrences"]["description"].lower()
    assert "occurrences" in (tools["list_all_tags"].description or "")


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("get_links", {"path": "a.md", "depth": 4}),
        ("get_links", {"path": "a.md", "direction": "sideways"}),
        ("search_content", {"query": ""}),
        ("search_content", {"query": "x", "limit": 0}),
        ("append_to_note", {"path": "a.md", "content": ""}),
        ("update_tags", {"path": "a.md", "add": ["has space"]}),
        ("list_vault_files", {"limit": 0}),
        ("get_daily_note", {"date": "2026-1-5"}),
        ("append_to_daily", {"content": "   "}),
    ],
)
async def test_invalid_arguments_come_back_as_errors(
    note_tools: MCPServer, name: str, args: dict[str, Any]
) -> None:
    assert (await call(note_tools, name, **args)).is_error


async def test_a_misspelled_argument_is_an_error_not_silently_dropped(fake: FakeVault) -> None:
    """`headng` used to be ignored: the text then landed at the end of the note."""
    fake.files["a.md"] = "# T\n\n## Log\n\nold\n"
    message = error_text(
        await call(real_server, "append_to_note", path="a.md", content="x", headng="Log")
    )
    assert "headng" in message and "Extra inputs are not permitted" in message
    assert error_text(await call(real_server, "get_links", path="a.md", extra="x"))
    assert fake.writes == [] and fake.files["a.md"] == "# T\n\n## Log\n\nold\n"
    for tool in (await tool_list(real_server)).values():
        assert tool.input_schema.get("additionalProperties") is False, tool.name


# --- list_vault_files / get_note -----------------------------------------------------------


async def test_list_vault_files_pages_with_total(fake: FakeVault, note_tools: MCPServer) -> None:
    fake.files.update({f"n{i}.md": "x" for i in (1, 2, 3)})
    first = data(await call(note_tools, "list_vault_files", limit=2))
    assert [f["path"] for f in first["files"]] == ["n1.md", "n2.md"]
    assert (first["total"], first["next_offset"]) == (3, 2)
    last = data(await call(note_tools, "list_vault_files", limit=2, offset=2))
    assert [f["path"] for f in last["files"]] == ["n3.md"] and last["next_offset"] is None


async def test_get_note_returns_a_structured_object(fake: FakeVault, note_tools: MCPServer) -> None:
    fake.files["a.md"] = "---\nstatus: 'NO'\n---\nBody\n"
    note = data(await call(note_tools, "get_note", path="a.md"))
    assert note["frontmatter"] == {"status": "NO"} and note["content"].endswith("Body\n")
    missing = await call(note_tools, "get_note", path="nope.md")
    assert "not found" in error_text(missing).lower()


async def test_domain_errors_are_not_success_shaped(fake: FakeVault, note_tools: MCPServer) -> None:
    result = await call(note_tools, "update_tags", path="nope.md", add=["x"])
    assert result.is_error and result.structured_content is None


# --- write_note / append_to_note / delete_note ---------------------------------------------


async def test_write_note_is_verbatim_and_reports_the_nfc_path(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    text = '$\\theta$ and print("a\\nb")\t---'
    assert NFD != NFC
    assert data(await call(note_tools, "write_note", path=NFD, content=text)) == {"path": NFC}
    assert fake.files == {NFC: text}
    again = await call(note_tools, "write_note", path=NFC, content="other")
    assert "already exists" in error_text(again)
    assert fake.files == {NFC: text}


async def test_append_to_note_goes_under_the_heading_and_reports_the_nfc_path(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files[NFC] = "# T\n\n## Log\n\nold\n"
    result = await call(note_tools, "append_to_note", path=NFD, content="new", heading="Log")
    assert data(result) == {"path": NFC, "heading": "Log"}
    assert fake.files[NFC] == "# T\n\n## Log\n\nold\nnew\n"
    missing = await call(note_tools, "append_to_note", path=NFC, content="x", heading="Nope")
    assert "not found" in error_text(missing).lower()
    assert "not found" in error_text(
        await call(note_tools, "append_to_note", path="gone.md", content="x")
    )


async def test_delete_note_trashes_by_default(fake: FakeVault, note_tools: MCPServer) -> None:
    fake.files["a.md"] = "x"
    result = data(await call(note_tools, "delete_note", path="a.md"))
    assert result == {"path": "a.md", "permanent": False} and fake.trashed == ["a.md"]


# --- update_tags ---------------------------------------------------------------------------


async def test_update_tags_noop_reports_nothing_and_does_not_write(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files["a.md"] = "---\ntags: [Alpha, beta]\n---\nB\n"
    result = await call(note_tools, "update_tags", path="a.md", add=["#alpha"], remove=["missing"])
    assert data(result) == {"path": "a.md", "tags": ["Alpha", "beta"], "added": [], "removed": []}
    assert fake.writes == []


async def test_update_tags_reports_only_the_real_changes(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files[NFC] = "---\ntags: [Alpha, beta]\n---\nB\n"
    result = await call(
        note_tools, "update_tags", path=NFD, add=["new", "#NEW", "ALPHA"], remove=["BETA", "nope"]
    )
    assert data(result) == {
        "path": NFC,  # the path get_note accepts, whichever way it was typed
        "tags": ["Alpha", "new"],
        "added": ["new"],
        "removed": ["beta"],
    }
    assert fake.writes == [NFC]


# --- list_all_tags / get_notes_by_tag ------------------------------------------------------


async def test_list_all_tags_ranks_by_occurrences_and_flags_truncation(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files.update({"a.md": "#top #top #a\n", "b.md": "#top #b\n"})
    result = await call(note_tools, "list_all_tags", limit=2)
    assert data(result) == {
        "tags": [{"tag": "top", "occurrences": 3}, {"tag": "a", "occurrences": 1}],
        "total": 3,
        "truncated": True,
    }


async def test_get_notes_by_tag_strips_hash_sorts_and_follows_nesting(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files.update({"b.md": "#work\n", "a.md": "#work/x #other\n", "c.md": "#nope\n"})
    result = await call(note_tools, "get_notes_by_tag", tag="#Work")
    assert data(result) == {"tag": "Work", "notes": ["a.md", "b.md"]}
    flat = await call(note_tools, "get_notes_by_tag", tag="work", include_nested=False)
    assert data(flat)["notes"] == ["b.md"]


# --- get_links -----------------------------------------------------------------------------


def edges(result: Any) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in data(result)["edges"]}


async def test_get_links_dedupes_edges_and_keeps_cycle_back_edges(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files.update(
        {
            "c1.md": "[[c2]] [[c2]] [[c3]] [[Nowhere]]",
            "c2.md": "[[c3]] [[c1]]",
            "c3.md": "[[c1]] [[c4]]",
            "c4.md": "[[c5]]",
            "c5.md": "end",
        }
    )
    result = await call(note_tools, "get_links", path="c1.md", direction="outgoing", depth=3)
    found = data(result)
    assert len(found["edges"]) == len(edges(result)) == 7  # no duplicates
    assert edges(result) == {
        ("c1.md", "c2.md"),
        ("c1.md", "c3.md"),
        ("c2.md", "c3.md"),
        ("c2.md", "c1.md"),
        ("c3.md", "c1.md"),
        ("c3.md", "c4.md"),
        ("c4.md", "c5.md"),
    }
    depths = {n["path"]: n["depth"] for n in found["nodes"]}
    assert depths == {"c1.md": 0, "c2.md": 1, "c3.md": 1, "c4.md": 2, "c5.md": 3}
    assert found["center"] == "c1.md" and found["truncated"] is False


async def test_get_links_depth_one_both_directions(fake: FakeVault, note_tools: MCPServer) -> None:
    fake.files.update({"a.md": "[[b]]", "b.md": "", "c.md": "[[a]]"})
    assert edges(await call(note_tools, "get_links", path="a.md")) == {
        ("a.md", "b.md"),
        ("c.md", "a.md"),
    }
    only_in = await call(note_tools, "get_links", path="a.md", direction="incoming")
    assert edges(only_in) == {("c.md", "a.md")}


async def test_get_links_unknown_start_note_is_an_error(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    for direction in ("outgoing", "incoming", "both"):
        result = await call(note_tools, "get_links", path="nope.md", direction=direction)
        assert "not found" in error_text(result).lower()


async def test_get_links_caps_the_node_count(
    fake: FakeVault, note_tools: MCPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(notes, "_MAX_GRAPH_NODES", 3)
    fake.files.update({"a.md": "[[b]] [[c]] [[d]] [[e]]", **{f"{n}.md": "" for n in "bcde"}})
    result = await call(note_tools, "get_links", path="a.md", direction="outgoing")
    found = data(result)
    assert len(found["nodes"]) == 3 and found["truncated"] is True
    assert all(t in {"b.md", "c.md"} for _, t in edges(result))  # no edge to a dropped node


# --- add_link ------------------------------------------------------------------------------


async def test_add_link_resolves_a_name_and_writes_the_shortest_text(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files.update(
        {
            "Reading List.md": "# R\n\n## See Also\n\nold\n\n## End\n",
            "Books/Fiction MOC.md": "x",
        }
    )
    result = await call(
        note_tools, "add_link", path="Reading List.md", target="Fiction MOC", heading="See Also"
    )
    assert data(result) == {
        "path": "Reading List.md",
        "target": "Books/Fiction MOC.md",
        "link": "[[Fiction MOC]]",
        "added": True,
    }
    text = fake.files["Reading List.md"]
    assert text.count("- [[Fiction MOC]]") == 1
    assert text.index("- [[Fiction MOC]]") < text.index("## End")  # inside the section


async def test_add_link_without_a_heading_keeps_the_trailing_newline(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files.update({"a.md": "- [[Other]]\n", "b.md": "text", "Plain.md": "x"})
    await call(note_tools, "add_link", path="a.md", target="Plain")
    await call(note_tools, "add_link", path="b.md", target="Plain")
    assert fake.files["a.md"] == "- [[Other]]\n- [[Plain]]\n"
    assert (
        fake.files["b.md"] == "text\n- [[Plain]]\n"
    )  # the fake appends a line; Vault keeps b's state


async def test_add_link_is_idempotent_whatever_the_existing_link_looks_like(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files.update({"a.md": "see [[Plain]]", "Books/Plain.md": "x"})
    for target in ("Plain", "Books/Plain.md"):
        assert (
            data(await call(note_tools, "add_link", path="a.md", target=target))["added"] is False
        )
    assert fake.writes == []


@pytest.mark.parametrize(
    "target", ["Plain]]\n## injected", "[[Plain]]", "Plain|alias", "Plain#Sec", "a\nb"]
)
async def test_add_link_rejects_link_syntax_and_injection(
    fake: FakeVault, note_tools: MCPServer, target: str
) -> None:
    fake.files.update({"a.md": "", "Plain.md": "x"})
    assert error_text(await call(note_tools, "add_link", path="a.md", target=target))
    assert fake.writes == []


async def test_add_link_to_a_missing_target_or_source_writes_nothing(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files.update({"a.md": "", "Plain.md": "x"})
    missing_target = await call(note_tools, "add_link", path="a.md", target="Nope")
    assert "no note" in error_text(missing_target).lower()
    missing_source = await call(note_tools, "add_link", path="gone.md", target="Plain")
    assert "not found" in error_text(missing_source).lower()
    assert fake.writes == []


async def test_add_link_refuses_a_target_whose_own_name_breaks_wikilinks(
    fake: FakeVault, note_tools: MCPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.files.update({"a.md": "", "Odd.md": "x"})

    async def awkward(target_path: str, source_path: str) -> str:
        return "Odd [draft]"

    monkeypatch.setattr(fake, "link_text", awkward)
    assert error_text(await call(note_tools, "add_link", path="a.md", target="Odd"))
    assert fake.writes == []


# --- search_content ------------------------------------------------------------------------


async def test_search_content_caps_matches_and_reports_truncation(
    fake: FakeVault, note_tools: MCPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    many = [SearchMatch(line=n, text=f"line {n}") for n in range(1, 31)]

    async def search(query: str, folder: str | None = None, limit: int = 20) -> SearchResults:
        hits = [SearchHit(path="a.md", matches=many), SearchHit(path="b.md", matches=[])]
        return SearchResults(hits=hits, truncated=True)

    monkeypatch.setattr(fake, "search", search)
    result = await call(note_tools, "search_content", query="line", limit=2)
    found = data(result)
    assert found["truncated"] is True and found["query"] == "line"
    first, second = found["hits"]
    assert first["match_count"] == 30 and len(first["matches"]) == 10
    assert first["matches"][0] == {"line": 1, "text": "line 1"}
    assert second == {"path": "b.md", "match_count": 0, "matches": []}


async def test_search_content_passes_folder_and_limit_through(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files.update({"in/a.md": "needle", "in/b.md": "needle", "out/c.md": "needle"})
    result = data(await call(note_tools, "search_content", query="needle", folder="in", limit=1))
    assert [h["path"] for h in result["hits"]] == ["in/a.md"] and result["truncated"] is True


# --- live: the real tools against a disposable vault ---------------------------------------


@pytest.mark.obsidian
async def test_live_a_note_is_written_edited_linked_and_deleted(
    vault: Vault, sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with live_tools(vault, sandbox, monkeypatch) as t:
        note = await t.put("Plan", "---\ntags: [draft]\n---\n# Plan\n\n## Tasks\n\nold\n")
        assert note == t.p("Plan.md")
        await t.ok("append_to_note", path=note, content="- ship it", heading="Tasks")
        changed = await t.ok("update_tags", path=note, add=["to-read"], remove=["DRAFT"])
        assert (changed["tags"], changed["added"], changed["removed"]) == (
            ["to-read"],
            ["to-read"],
            ["draft"],
        )
        name = f"Fiction MOC {uuid.uuid4().hex[:6]}"  # unique: the shortest link text is its name
        moc = await t.put(name, "x")
        added = await t.ok("add_link", path=note, target=name, heading="Tasks")
        assert (added["added"], added["link"], added["target"]) == (True, f"[[{name}]]", moc)
        assert await t.text(note) == (
            f"---\ntags:\n  - to-read\n---\n# Plan\n\n## Tasks\n\nold\n- ship it\n- [[{name}]]\n"
        )
        incoming = await t.ok("get_links", path=moc, direction="incoming")
        assert {(e["source"], e["target"]) for e in incoming["edges"]} == {(note, moc)}
        assert (await t.ok("add_link", path=note, target=name))["added"] is False
        assert (await t.ok("delete_note", path=note)) == {"path": note, "permanent": False}
        assert "not found" in (await t.err("get_note", path=note)).lower()


@pytest.mark.obsidian
async def test_live_a_misspelled_argument_writes_nothing(
    vault: Vault, sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with live_tools(vault, sandbox, monkeypatch) as t:
        note = await t.put("Log", "# T\n\n## Tasks\n\nold\n")
        message = await t.err("append_to_note", path=note, content="x", headng="Tasks")
        assert "Extra inputs are not permitted" in message
        assert await t.text(note) == "# T\n\n## Tasks\n\nold\n"


@pytest.mark.obsidian
async def test_live_tag_counts_are_occurrences_not_notes(
    vault: Vault, sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = uuid.uuid4().hex[:6]
    async with live_tools(vault, sandbox, monkeypatch) as t:
        await t.put("Twice.md", f"#nd-{key} and again #nd-{key}\n")
        await t.put("Once.md", f"#nd-{key}\n")
        tags = (await t.ok("list_all_tags", limit=1000))["tags"]
        assert {x["tag"]: x["occurrences"] for x in tags}[f"nd-{key}"] == 3
        assert len((await t.ok("get_notes_by_tag", tag=f"nd-{key}"))["notes"]) == 2


@pytest.mark.obsidian
async def test_live_search_cuts_a_long_line_around_the_match(
    vault: Vault, sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = f"zq{uuid.uuid4().hex[:8]}"
    async with live_tools(vault, sandbox, monkeypatch) as t:
        await t.put("long.md", f"{'a' * 2000} {token} {'b' * 2000}\n")

        async def found() -> None:
            assert (await t.ok("search_content", query=token, folder=sandbox.dir))["hits"]

        await eventually(found)
        (hit,) = (await t.ok("search_content", query=token, folder=sandbox.dir))["hits"]
        (match,) = hit["matches"]
        assert token in match["text"] and len(match["text"]) <= 302
        assert match["text"].startswith("…") and match["text"].endswith("…")
        assert "control" in await t.err("search_content", query="a\x00b")


@pytest.mark.obsidian
async def test_live_an_nfd_path_comes_back_as_the_nfc_path_get_note_accepts(
    vault: Vault, sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with live_tools(vault, sandbox, monkeypatch) as t:
        wrote = await t.ok("write_note", path=t.p(NFD), content="---\ntags: [a]\n---\nB\n")
        assert wrote["path"] == t.p(NFC)
        for spelling in (t.p(NFD), wrote["path"]):
            assert (await t.ok("get_note", path=spelling))["path"] == t.p(NFC)
        assert (await t.ok("update_tags", path=t.p(NFD), add=["b"]))["path"] == t.p(NFC)
        assert (await t.ok("append_to_note", path=t.p(NFD), content="x"))["path"] == t.p(NFC)


@pytest.mark.obsidian
async def test_live_errors_never_show_the_vault_path(
    vault: Vault, cli: ObsidianCLI, sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = str(await cli.eval("return app.vault.adapter.basePath;"))
    async with live_tools(vault, sandbox, monkeypatch) as t:
        message = await t.err("write_note", path=t.p("n" * 300), content="x")
        assert base not in message and "ENAMETOOLONG" in message
