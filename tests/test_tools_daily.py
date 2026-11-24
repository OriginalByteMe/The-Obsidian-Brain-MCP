"""Tests for the daily note tools.

The plain tests drive the tools through an in-memory MCP client against the in-memory
`FakeVault`, so they need no Obsidian. The `obsidian` tests at the bottom run the real tools
against the disposable vault; the daily-notes plugin is pointed at the test's sandbox folder
(`daily_config`), so nothing outside it is created.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from mcp.server.mcpserver import MCPServer

from obsidian_brain.tools import daily
from obsidian_brain.vault import Vault

from .conftest import Sandbox, call, data, error_text, live_tools
from .fake_vault import FakeVault

PAST = dt.date(2026, 11, 22)
PAST_PATH = "Daily/2026-11-22.md"

# --- entry rendering -----------------------------------------------------------------------


def test_timestamped_entry_has_content_then_links_then_tags() -> None:
    entry = daily.render_entry("Shipped it", ["work", "#ship"], ["Plan", "Team/Notes"], "10:30")
    assert entry == "- 10:30 Shipped it [[Plan]] [[Team/Notes]] #work #ship"


def test_plain_entry_is_the_content_untouched() -> None:
    assert daily.render_entry("  keep **as is**\n\nsecond para ", [], [], None) == (
        "keep **as is**\n\nsecond para"
    )


def test_multiline_timestamped_entry_stays_inside_its_bullet() -> None:
    entry = daily.render_entry("line one\nline two", ["t"], [], "09:05")
    assert entry == "- 09:05 line one\n  line two #t"


# --- dates ---------------------------------------------------------------------------------


def test_day_parses_and_defaults_to_today() -> None:
    assert daily._day("2026-11-22") == PAST
    assert daily._day(None) == dt.date.today()


@pytest.mark.parametrize("bad", ["2026-02-30", "2026-13-01", "0000-00-00"])
async def test_impossible_dates_are_errors_even_though_they_match_the_pattern(
    fake: FakeVault, note_tools: MCPServer, bad: str
) -> None:
    assert "not a real date" in error_text(await call(note_tools, "get_daily_note", date=bad))
    assert "not a real date" in error_text(
        await call(note_tools, "append_to_daily", content="x", date=bad)
    )
    assert fake.files == {}


async def test_malformed_dates_are_rejected_by_the_schema(note_tools: MCPServer) -> None:
    for bad in ("2026-1-5", "yesterday", "22/11/2026", ""):
        assert (await call(note_tools, "get_daily_note", date=bad)).is_error


# --- get_daily_note never creates ----------------------------------------------------------


async def test_get_daily_note_reports_a_missing_note_without_creating_it(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    result = await call(note_tools, "get_daily_note", date="2026-11-22")
    assert data(result) == {"date": "2026-11-22", "path": PAST_PATH, "exists": False, "note": None}
    assert fake.files == {} and fake.writes == []


async def test_get_daily_note_returns_the_note_of_that_day(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    fake.files[PAST_PATH] = "# Yesterday\n"
    fake.files[f"Daily/{dt.date.today().isoformat()}.md"] = "today"
    found = data(await call(note_tools, "get_daily_note", date="2026-11-22"))
    assert found["exists"] is True and found["path"] == PAST_PATH
    assert found["note"]["content"] == "# Yesterday\n"


async def test_get_daily_note_defaults_to_today(fake: FakeVault, note_tools: MCPServer) -> None:
    found = data(await call(note_tools, "get_daily_note"))
    assert found["date"] == dt.date.today().isoformat()


# --- append_to_daily: date targeting, entry format, heading --------------------------------


async def test_append_to_daily_writes_the_note_of_the_requested_past_date(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    result = await call(
        note_tools, "append_to_daily", content="Finished the report", date="2026-11-22"
    )
    assert data(result) == {"date": "2026-11-22", "path": PAST_PATH, "entry": "Finished the report"}
    assert fake.files == {PAST_PATH: "Finished the report"}  # not today's note


async def test_append_to_daily_timestamp_entry_format(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    result = await call(
        note_tools,
        "append_to_daily",
        content="Finished the report",
        timestamp=True,
        tags=["work"],
        links=["Quarterly Report"],
    )
    entry = data(result)["entry"]
    assert re.fullmatch(r"- \d\d:\d\d Finished the report \[\[Quarterly Report\]\] #work", entry)
    assert list(fake.files.values()) == [entry]


async def test_the_heading_is_stripped_and_sent_to_the_vault_which_creates_it(
    fake: FakeVault, note_tools: MCPServer
) -> None:
    for text in ("first", "second"):
        await call(note_tools, "append_to_daily", content=text, date="2026-11-22", heading=" Log ")
    assert fake.files[PAST_PATH] == "## Log\n\nfirst\nsecond"
    await call(
        note_tools, "append_to_daily", content="deep", date="2026-11-22", heading="### Deep dive"
    )
    assert fake.files[PAST_PATH].endswith("\n\n### Deep dive\n\ndeep")


async def test_heading_must_be_one_line(fake: FakeVault, note_tools: MCPServer) -> None:
    result = await call(note_tools, "append_to_daily", content="x", heading="Log\n## Injected")
    assert result.is_error and fake.files == {}


# --- live: the real tools against a disposable vault ---------------------------------------


@pytest.mark.obsidian
async def test_live_get_daily_note_reports_a_missing_note_and_creates_nothing(
    vault: Vault, sandbox: Sandbox, daily_config: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with live_tools(vault, sandbox, monkeypatch) as t:
        result = await t.ok("get_daily_note", date="1999-01-02")
        assert result["date"] == "1999-01-02"
        assert result["path"] == f"{daily_config['folder']}/1999/01/1999-01-02.md"
        assert result["exists"] is False and result["note"] is None
        assert "not found" in (await t.err("get_note", path=result["path"])).lower()
        assert (await t.ok("get_daily_note", date="1999-01-02"))["exists"] is False


@pytest.mark.obsidian
async def test_live_append_to_daily_writes_the_requested_past_day(
    vault: Vault, sandbox: Sandbox, daily_config: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with live_tools(vault, sandbox, monkeypatch) as t:
        result = await t.ok(
            "append_to_daily",
            content="Finished the report",
            date="1999-03-04",
            timestamp=True,
            tags=["#work"],
            links=["Quarterly Report"],
        )
        assert result["date"] == "1999-03-04"
        assert result["path"] == f"{daily_config['folder']}/1999/03/1999-03-04.md"
        assert re.fullmatch(
            r"- \d\d:\d\d Finished the report \[\[Quarterly Report\]\] #work", result["entry"]
        )
        read = (await t.ok("get_daily_note", date="1999-03-04"))["note"]
        assert read["content"].endswith(f"## Log\n{result['entry']}")  # the template's heading
        assert read["tags"] == ["work"] and read["path"] == result["path"]


@pytest.mark.obsidian
async def test_live_a_missing_heading_is_created_once_then_reused(
    vault: Vault, sandbox: Sandbox, daily_config: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with live_tools(vault, sandbox, monkeypatch) as t:
        for text in ("first", "second"):
            await t.ok("append_to_daily", content=text, date="1999-05-06", heading="Notes")
        await t.ok("append_to_daily", content="deep", date="1999-05-06", heading="## Deep dive")
        await t.ok("append_to_daily", content="third", date="1999-05-06", heading="## notes")
        content = (await t.ok("get_daily_note", date="1999-05-06"))["note"]["content"]
        assert content.endswith("## Notes\n\nfirst\nsecond\nthird\n\n## Deep dive\n\ndeep")
        assert content.count("## Notes") == 1
