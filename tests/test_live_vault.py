"""Vault operations against the real Obsidian CLI and a disposable test vault.

Opt-in: `OBSIDIAN_TEST_VAULT=obsidian-mcp-testvault uv run pytest -m obsidian tests/test_live_vault.py`.
Each test works in its own sandbox folder (see conftest.py). Byte-exactness is checked
two ways: through `read_note(...).content` and by reading the file straight off the disk.
"""

from __future__ import annotations

import asyncio
import json
import time
import unicodedata
import uuid
from datetime import date

import pytest

from obsidian_brain.exceptions import (
    ContentTooLargeError,
    HeadingNotFoundError,
    InvalidArgumentError,
    NoteExistsError,
    NoteNotFoundError,
    ObsidianCLIError,
)
from obsidian_brain.obsidian import ObsidianCLI
from obsidian_brain.vault import Vault

from .conftest import BINARY, LocalTrash, Sandbox, eventually, put

pytestmark = pytest.mark.obsidian


async def exists(vault: Vault, path: str) -> bool:
    """Whether `path` is a note the vault can read."""
    try:
        await vault.read_note(path)
    except NoteNotFoundError:
        return False
    return True


TRICKY = {
    "backslash_n_t": "literal \\n and \\t and \\\\ and \\r here\nsecond line\n",
    "latex": "Inline $\\theta$ and $$\\frac{a}{b} \\\\ \\alpha$$\n\n\\begin{align} x &= 1 \\\\ y \\end{align}\n",
    "crlf": "# Title\r\n\r\nline one\r\nline two\r\n",
    "bom": "\ufeff# BOM note\nbody\n",
    "bom_crlf_frontmatter": "\ufeff---\r\ntitle: x\r\ntags: [a]\r\n---\r\nBody\r\n",
    "unicode": "日本語 😀 \u2028 é ñ \u00a0 end",
    "js_and_shell": "${process.exit()} `backtick` $(rm -rf /) 'q' \"dq\" </script> %s %d\n",
    "no_trailing_newline": "no newline at the end",
    "empty": "",
}


# ---------------------------------------------------------------------------
# list_files / exists / read_note / write_note / delete
# ---------------------------------------------------------------------------


class TestFiles:
    async def test_list_files_recursive_filtered_and_sorted(self, vault, cli, sandbox: Sandbox):
        await put(cli, sandbox.path("b.md"), "b")
        await put(cli, sandbox.path("sub/a.md"), "aa")
        await put(cli, sandbox.path("sub/deep/c.txt"), "ccc")
        await put(cli, sandbox.path("img.png"), b"\x89PNG\x00\xff")

        everything = await vault.list_files(sandbox.dir)
        assert [f.path for f in everything] == sorted(
            sandbox.path(n) for n in ["b.md", "img.png", "sub/a.md", "sub/deep/c.txt"]
        )
        by_path = {f.path: f for f in everything}
        assert by_path[sandbox.path("sub/a.md")].size == 2
        assert by_path[sandbox.path("sub/a.md")].extension == "md"
        assert by_path[sandbox.path("sub/a.md")].modified.tzinfo is not None

        assert [f.path for f in await vault.list_files(sandbox.dir + "/")] == [
            f.path for f in everything
        ]
        assert [f.path for f in await vault.list_files(sandbox.path("sub"))] == [
            sandbox.path("sub/a.md"),
            sandbox.path("sub/deep/c.txt"),
        ]
        only_md = await vault.list_files(sandbox.dir, extension=".MD")
        assert [f.path for f in only_md] == [sandbox.path("b.md"), sandbox.path("sub/a.md")]

    async def test_list_files_root_and_missing_folder(self, vault, sandbox: Sandbox):
        assert len(await vault.list_files("")) == len(await vault.list_files("/")) > 0
        with pytest.raises(NoteNotFoundError, match="Folder not found"):
            await vault.list_files(sandbox.path("nope"))

    async def test_read_missing_note(self, vault, sandbox: Sandbox):
        with pytest.raises(NoteNotFoundError, match="Note not found"):
            await vault.read_note(sandbox.path("missing.md"))

    async def test_read_binary_file_is_rejected(self, vault, cli, sandbox: Sandbox):
        await put(cli, sandbox.path("img.png"), b"\x89PNG\r\n\x1a\n\x00\xff\xfe\xfd")
        with pytest.raises(InvalidArgumentError, match="not a text file"):
            await vault.read_note(sandbox.path("img.png"))

    async def test_read_other_text_types_and_empty_note(self, vault, cli, sandbox: Sandbox):
        await put(cli, sandbox.path("data.json"), '{"a": 1}')
        await put(cli, sandbox.path("empty.md"), "")
        data = await vault.read_note(sandbox.path("data.json"))
        assert data.content == '{"a": 1}' and data.frontmatter == {} and data.tags == []
        empty = await vault.read_note(sandbox.path("empty.md"))
        assert empty.content == "" and empty.size == 0 and empty.headings == []

    async def test_read_note_has_fresh_metadata_right_after_write(self, vault, sandbox: Sandbox):
        path = await vault.write_note(
            sandbox.path("fresh"),
            "---\ntitle: T\ntags: [fm]\nrel: '[[Other]]'\n---\n# Heading\n\nSee [[Other#Sec|x]] ![[emb]] #inline\n\n## Sub\n",
        )
        note = await vault.read_note(
            path
        )  # no waiting: read_note waits for Obsidian's parse itself
        assert note.frontmatter["title"] == "T"
        assert note.tags == ["inline", "fm"]
        assert note.headings == ["Heading", "Sub"]
        assert {(link.kind, link.link) for link in note.links} == {
            ("link", "Other#Sec"),
            ("embed", "emb"),
            ("frontmatter", "Other"),
        }

    @pytest.mark.parametrize("content", TRICKY.values(), ids=TRICKY.keys())
    async def test_write_note_round_trips_exact_bytes(self, vault, disk, sandbox: Sandbox, content):
        path = await vault.write_note(sandbox.path("rt.md"), content)
        assert path == sandbox.path("rt.md")
        assert disk(path) == content.encode()
        assert (await vault.read_note(path)).content == content

    async def test_write_note_adds_md_creates_folders_returns_final_path(
        self, vault, disk, sandbox: Sandbox
    ):
        assert await vault.write_note(sandbox.path("a/b/c/Note"), "x") == sandbox.path(
            "a/b/c/Note.md"
        )
        assert disk(sandbox.path("a/b/c/Note.md")) == b"x"

    @pytest.mark.parametrize(
        "title",
        [
            "Meeting 2024.11.23",
            "Learning Node.js",
            "Project.Alpha",
            "J.R",
            "notes.final",
            "data.json",
        ],
    )
    async def test_a_dotted_title_is_not_an_extension(self, vault, sandbox: Sandbox, title):
        assert await vault.write_note(sandbox.path(title), "y") == sandbox.path(f"{title}.md")
        assert (await vault.read_note(sandbox.path(f"{title}.md"))).content == "y"

    @pytest.mark.parametrize(
        "name", ["UPPER.MD", "Board.canvas", "scan.PDF", "pic.png", "clip.mp4"]
    )
    async def test_a_file_type_obsidian_opens_is_kept(self, vault, sandbox: Sandbox, name):
        assert await vault.write_note(sandbox.path(name), "z") == sandbox.path(name)

    async def test_nfd_paths_are_normalised_to_nfc_everywhere(self, vault, disk, sandbox: Sandbox):
        nfd = sandbox.path(unicodedata.normalize("NFD", "résumé finder.md"))
        nfc = unicodedata.normalize("NFC", nfd)
        assert nfd != nfc
        assert await vault.write_note(nfd, "---\ntags: [a]\n---\nbody\n") == nfc
        assert disk(nfc) == b"---\ntags: [a]\n---\nbody\n"
        for spelling in (nfd, nfc):  # the same note whichever way it is spelled
            assert (await vault.read_note(spelling)).path == nfc
        await vault.append(nfd, "more")
        assert (await vault.update_tags(nfd, add=["b"])).added == ["b"]
        assert [f.path for f in await vault.list_files(sandbox.dir)] == [nfc]
        assert await vault.backlinks(nfd) == []
        await vault.delete(nfd, permanent=True)
        assert not await exists(vault, nfc)

    async def test_write_note_never_dedupes_and_never_overwrites_silently(
        self, vault, disk, sandbox: Sandbox
    ):
        path = sandbox.path("once.md")
        await vault.write_note(path, "first")
        with pytest.raises(NoteExistsError, match="overwrite=true"):
            await vault.write_note(path, "second")
        assert disk(path) == b"first"
        assert [f.path for f in await vault.list_files(sandbox.dir)] == [path]  # no "once 1.md"
        assert await vault.write_note(path, "second\r\n\ufeff", overwrite=True) == path
        assert disk(path) == "second\r\n\ufeff".encode()

    async def test_overwrite_true_creates_when_missing(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(sandbox.path("new.md"), "n", overwrite=True)
        assert disk(path) == b"n"

    async def test_concurrent_creates_of_one_path_yield_exactly_one_winner(
        self, vault, disk, sandbox: Sandbox
    ):
        path = sandbox.path("race.md")
        results = await asyncio.gather(
            *(vault.write_note(path, f"writer-{i}") for i in range(6)), return_exceptions=True
        )
        assert sum(isinstance(r, str) for r in results) == 1
        assert all(isinstance(r, NoteExistsError) for r in results if not isinstance(r, str))
        assert disk(path).startswith(b"writer-")

    @pytest.mark.parametrize(
        "path",
        ["", "/abs.md", "../escape.md", "a/../b.md", "a/./b.md", "a//b.md", ".obsidian/x.md", ".hidden/x.md",
         "a\\b.md", "C:/x.md", "line\nbreak.md", "tab\t.md", "nul\x00.md", "folder/"],
    )  # fmt: skip
    async def test_invalid_paths_are_rejected_and_nothing_is_written(
        self, vault, sandbox: Sandbox, path
    ):
        before = await vault.list_files("")
        with pytest.raises(InvalidArgumentError):
            await vault.write_note(path, "x")
        with pytest.raises(InvalidArgumentError):
            await vault.read_note(path)
        assert await vault.list_files("") == before

    async def test_content_over_one_megabyte_is_a_clean_error(self, vault, sandbox: Sandbox):
        path = sandbox.path("huge.md")
        with pytest.raises(ContentTooLargeError, match="at most 900 KB"):
            await vault.write_note(path, "x" * 1_048_577)
        assert not await exists(vault, path)

    async def test_large_note_just_under_the_ceiling_round_trips(
        self, vault, disk, sandbox: Sandbox
    ):
        content = ("line of text é " * 60_000)[:800_000]
        path = await vault.write_note(sandbox.path("big.md"), content)
        assert disk(path) == content.encode()
        assert (await vault.read_note(path)).content == content

    async def test_delete_goes_to_trash_by_default(
        self, vault, cli, local_trash: LocalTrash, sandbox: Sandbox
    ):
        name = local_trash.name("bye")
        path = await vault.write_note(sandbox.path(name), "kept in the trash")
        await vault.delete(path)
        assert not await exists(vault, path)
        assert await local_trash.text(name) == "kept in the trash"

    async def test_permanent_delete_skips_the_trash_and_a_missing_note_is_an_error(
        self, vault, disk, local_trash: LocalTrash, sandbox: Sandbox
    ):
        name = local_trash.name("gone")
        path = await vault.write_note(sandbox.path(name), "x")
        await vault.delete(path, permanent=True)
        assert not await exists(vault, path)
        assert await local_trash.text(name) is None
        with pytest.raises(FileNotFoundError):
            disk(path)
        with pytest.raises(NoteNotFoundError):
            await vault.delete(path)


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------


class TestAppend:
    async def test_separates_by_exactly_one_newline(self, vault, disk, sandbox: Sandbox):
        await vault.write_note(sandbox.path("with-nl.md"), "a\n")
        await vault.write_note(sandbox.path("no-nl.md"), "a")
        await vault.write_note(sandbox.path("blank.md"), "a\n\n")
        await vault.write_note(sandbox.path("empty.md"), "")
        for name in ("with-nl", "no-nl", "blank", "empty"):
            await vault.append(sandbox.path(f"{name}.md"), "b")
        assert disk(sandbox.path("with-nl.md")) == b"a\nb"
        assert disk(sandbox.path("no-nl.md")) == b"a\nb"
        assert disk(sandbox.path("blank.md")) == b"a\n\nb"
        assert disk(sandbox.path("empty.md")) == b"b"

    @pytest.mark.parametrize(
        "content", [c for c in TRICKY.values() if c], ids=[k for k, c in TRICKY.items() if c]
    )
    async def test_appended_content_is_stored_exactly(self, vault, disk, sandbox: Sandbox, content):
        await vault.write_note(sandbox.path("n.md"), "head\n")
        await vault.append(sandbox.path("n.md"), content)
        assert disk(sandbox.path("n.md")) == b"head\n" + content.encode()

    async def test_preserves_crlf_and_bom_of_the_existing_file(self, vault, disk, sandbox: Sandbox):
        original = "\ufeff---\r\ntags: [a]\r\n---\r\nBody\r\nlast"
        await vault.write_note(sandbox.path("n.md"), original)
        await vault.append(sandbox.path("n.md"), "added")
        assert disk(sandbox.path("n.md")) == (original + "\r\nadded").encode()

    async def test_missing_note(self, vault, sandbox: Sandbox):
        with pytest.raises(NoteNotFoundError):
            await vault.append(sandbox.path("nope.md"), "x")
        with pytest.raises(NoteNotFoundError):
            await vault.append(sandbox.path("nope.md"), "x", heading="## H")

    async def test_a_binary_file_is_refused_and_its_bytes_are_never_rewritten(
        self, vault, cli, disk, sandbox: Sandbox
    ):
        for name in ("pic.png", "pic.md"):  # `.md` in the name does not make bytes text
            path = sandbox.path(name)
            await put(cli, path, BINARY)
            for kwargs in (
                {},
                {"as_line": True},
                {"heading": "## H"},
                {"heading": "H", "create_heading": True},
            ):
                with pytest.raises(InvalidArgumentError, match="not a text file"):
                    await vault.append(path, "oops", **kwargs)
            assert disk(path) == BINARY

    NOTE = "# Title\n\n## Notes\n\nold\n\n### Deeper\n\ndeep text\n\n## Other\n\nx\n"

    async def test_heading_append_goes_to_the_end_of_the_section(
        self, vault, disk, sandbox: Sandbox
    ):
        path = await vault.write_note(sandbox.path("h.md"), self.NOTE)
        await vault.append(path, "N1", heading="## Notes")
        await vault.append(path, "N2", heading="## Notes")
        # inside "## Notes" after its subsection, before "## Other"; blank line before the next heading kept
        assert disk(path).decode() == (
            "# Title\n\n## Notes\n\nold\n\n### Deeper\n\ndeep text\nN1\nN2\n\n## Other\n\nx\n"
        )

    async def test_heading_forms_and_case(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(sandbox.path("h.md"), self.NOTE)
        await vault.append(path, "bare", heading="notes")  # no #s, any case, any level
        await vault.append(path, "deeper", heading="### Deeper")  # level given and matching
        text = disk(path).decode()
        # both sections end at "## Other": "bare" went to the end of "## Notes" (after its
        # subsection), "deeper" to the end of "### Deeper": the same place, after "bare"
        assert "deep text\nbare\ndeeper\n\n## Other" in text
        with pytest.raises(HeadingNotFoundError):
            await vault.append(path, "x", heading="# Notes")  # wrong level
        with pytest.raises(HeadingNotFoundError):
            await vault.append(path, "x", heading="## Absent")
        assert disk(path).decode() == text  # failed appends changed nothing

    async def test_last_section_empty_section_and_crlf(self, vault, disk, sandbox: Sandbox):
        await vault.write_note(sandbox.path("last.md"), "# A\n\n## Last\nstuff")
        await vault.append(sandbox.path("last.md"), "more", heading="Last")
        assert disk(sandbox.path("last.md")) == b"# A\n\n## Last\nstuff\nmore"
        await vault.write_note(sandbox.path("empty.md"), "## S\n## T\n")
        await vault.append(sandbox.path("empty.md"), "in S", heading="## S")
        assert disk(sandbox.path("empty.md")) == b"## S\nin S\n## T\n"
        await vault.write_note(sandbox.path("crlf.md"), "## S\r\nold\r\n\r\n## T\r\nz\r\n")
        await vault.append(sandbox.path("crlf.md"), "new", heading="## S")
        assert disk(sandbox.path("crlf.md")) == b"## S\r\nold\r\nnew\r\n\r\n## T\r\nz\r\n"

    async def test_heading_only_inside_a_code_fence_or_frontmatter_is_not_found(
        self, vault, disk, sandbox: Sandbox
    ):
        fenced = "# Real\n\n```md\n## Fake\n```\n\ntext\n"
        await vault.write_note(sandbox.path("fence.md"), fenced)
        with pytest.raises(HeadingNotFoundError):
            await vault.append(sandbox.path("fence.md"), "x", heading="## Fake")
        assert disk(sandbox.path("fence.md")).decode() == fenced
        commented = "---\n# Notes\ntags: [a]\n---\nBody\n"
        await vault.write_note(sandbox.path("yaml.md"), commented)
        with pytest.raises(HeadingNotFoundError):
            await vault.append(sandbox.path("yaml.md"), "x", heading="# Notes")
        assert disk(sandbox.path("yaml.md")).decode() == commented

    async def test_eight_concurrent_appends_lose_nothing(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(sandbox.path("c.md"), "start\n")
        await asyncio.gather(*(vault.append(path, f"line{i}") for i in range(8)))
        lines = disk(path).decode().split("\n")
        assert lines[0] == "start" and sorted(lines[1:]) == sorted(f"line{i}" for i in range(8))

    async def test_eight_concurrent_heading_appends_lose_nothing(
        self, vault, disk, sandbox: Sandbox
    ):
        path = await vault.write_note(sandbox.path("c.md"), "# T\n\n## S\n\nold\n\n## Z\n\nz\n")
        await asyncio.gather(*(vault.append(path, f"h{i}", heading="## S") for i in range(8)))
        text = disk(path).decode()
        section = text.split("## S\n")[1].split("\n\n## Z")[0].split("\n")
        assert section[:2] == ["", "old"] and sorted(section[2:]) == sorted(
            f"h{i}" for i in range(8)
        )
        assert text.endswith("\n\n## Z\n\nz\n")

    async def test_heading_append_in_a_note_that_starts_with_a_bom(
        self, vault, disk, sandbox: Sandbox
    ):
        """Obsidian counts heading offsets from after the BOM."""
        path = await vault.write_note(sandbox.path("bom.md"), "\ufeff# T\n\n## S\n\nold\n\n## Z\n")
        await vault.append(path, "x", heading="## S")
        assert disk(path) == "\ufeff# T\n\n## S\n\nold\nx\n\n## Z\n".encode()

    async def test_as_line_keeps_the_trailing_newline_state_of_the_note(
        self, vault, disk, sandbox: Sandbox
    ):
        for name, before, after in [
            ("nl", "a\n", "a\n- x\n"),
            ("no-nl", "a", "a\n- x"),
            ("empty", "", "- x"),
            ("crlf", "a\r\n", "a\r\n- x\r\n"),
            ("blank", "a\n\n", "a\n\n- x\n"),
        ]:
            path = await vault.write_note(sandbox.path(f"{name}.md"), before)
            await vault.append(path, "- x", as_line=True)
            assert disk(path).decode() == after, name

    async def test_create_heading_adds_a_missing_section_at_the_end(
        self, vault, disk, sandbox: Sandbox
    ):
        for name, before, heading, after in [
            ("text", "intro\n", "Log", "intro\n\n## Log\n\nx"),
            ("no-nl", "intro", "### Deep dive", "intro\n\n### Deep dive\n\nx"),
            ("empty", "", "## Log", "## Log\n\nx"),
            ("crlf", "intro\r\n", "Log", "intro\r\n\r\n## Log\r\n\r\nx"),
            (
                "level",
                "# T\n\n## S\n",
                "# S",
                "# T\n\n## S\n\n# S\n\nx",
            ),  # wrong level: new heading
        ]:
            path = await vault.write_note(sandbox.path(f"{name}.md"), before)
            await vault.append(path, "x", heading=heading, create_heading=True)
            assert disk(path).decode() == after, name

    async def test_create_heading_reuses_an_existing_section(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(sandbox.path("n.md"), "# T\n\n## Log\n\nold\n\n## Z\n")
        await vault.append(path, "x", heading="log", create_heading=True)
        assert disk(path).decode() == "# T\n\n## Log\n\nold\nx\n\n## Z\n"
        with pytest.raises(HeadingNotFoundError):  # without the flag a missing heading is an error
            await vault.append(path, "y", heading="Absent")
        assert disk(path).decode() == "# T\n\n## Log\n\nold\nx\n\n## Z\n"

    async def test_concurrent_calls_create_one_heading(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(sandbox.path("race.md"), "intro\n")
        await asyncio.gather(
            *(vault.append(path, f"e{i}", heading="Race", create_heading=True) for i in range(4))
        )
        text = disk(path).decode()
        assert text.count("## Race") == 1 and text.startswith("intro\n\n## Race\n\n")
        assert sorted(text.split("## Race\n\n")[1].split("\n")) == ["e0", "e1", "e2", "e3"]

    async def test_os_errors_do_not_leak_the_vault_path(self, vault, cli, sandbox: Sandbox):
        base = str(await cli.eval("return app.vault.adapter.basePath;"))
        with pytest.raises(ObsidianCLIError) as caught:
            await vault.write_note(sandbox.path("n" * 300 + ".md"), "x")
        message = str(caught.value)
        assert base not in message and sandbox.dir in message  # relative path only


# ---------------------------------------------------------------------------
# update_tags
# ---------------------------------------------------------------------------

YAML_NOTE = (
    "---\ncountry: NO\nzip: 01234\nwhen: 10:30\nnul: ~\n# keep me\nzeta: 1\nalpha: 2\n"
    "version: 1.10\nhex: 0x1F\ntags: [a]\n---\nBody\n"
)


class TestUpdateTags:
    async def test_only_the_tags_entry_changes(self, vault, disk, sandbox: Sandbox):
        """NO, 01234, 10:30, ~, 1.10, 0x1F, the comment and the key order are untouched."""
        path = await vault.write_note(sandbox.path("y.md"), YAML_NOTE)
        change = await vault.update_tags(path, add=["#new"])
        assert disk(path).decode() == YAML_NOTE.replace("tags: [a]", "tags:\n  - a\n  - new")
        assert (change.tags, change.added, change.removed) == (["a", "new"], ["new"], [])
        # metadata is fresh at once: no waiting before reading it back
        assert (await vault.read_note(path)).frontmatter["tags"] == ["a", "new"]

    async def test_noop_edits_leave_the_file_alone(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(sandbox.path("y.md"), YAML_NOTE)
        before = (await vault.read_note(path)).modified
        change = await vault.update_tags(path, add=["A"], remove=["nothere"])
        assert (change.tags, change.added, change.removed) == (["a"], [], [])
        assert disk(path).decode() == YAML_NOTE
        assert (await vault.read_note(path)).modified == before

    async def test_the_result_comes_from_the_same_eval_as_the_edit(
        self, vault, sandbox: Sandbox, monkeypatch
    ):
        path = await vault.write_note(sandbox.path("y.md"), "---\ntags: [a, b]\n---\nB")
        evals: list[str] = []
        real = vault.cli.eval

        async def counting(body, *args, **kwargs):
            evals.append(body)
            return await real(body, *args, **kwargs)

        monkeypatch.setattr(vault.cli, "eval", counting)
        change = await vault.update_tags(path, add=["c", "A"], remove=["B", "zz"])
        assert len(evals) == 1
        assert (change.tags, change.added, change.removed) == (["a", "c"], ["c"], ["b"])

    @pytest.mark.parametrize(
        ("before", "after"),
        [
            ("---\ntags: [a]\n---\nB", "---\ntags:\n  - a\n  - b\n---\nB"),
            ("---\ntags: ['a', \"c d\"]\n---\nB", "---\ntags:\n  - a\n  - \"c d\"\n  - b\n---\nB"),
            ("---\ntags:\n  - a\n---\nB", "---\ntags:\n  - a\n  - b\n---\nB"),
            ("---\ntags:\n- a\n---\nB", "---\ntags:\n  - a\n  - b\n---\nB"),
            ("---\ntags:\n    - a   # why\n---\nB", "---\ntags:\n  - a\n  - b\n---\nB"),
            ("---\ntags: a\n---\nB", "---\ntags:\n  - a\n  - b\n---\nB"),
            ("---\ntags: a, x z\n---\nB", "---\ntags:\n  - a\n  - x\n  - z\n  - b\n---\nB"),
            ("---\ntags:\n---\nB", "---\ntags:\n  - b\n---\nB"),
            ("---\ntitle: T\n---\nB", "---\ntitle: T\ntags:\n  - b\n---\nB"),
            ("---\ntags: [a]\ntitle: T\n---\nB", "---\ntags:\n  - a\n  - b\ntitle: T\n---\nB"),
            ("---\ntag: a\n---\nB", "---\ntag: a\ntags:\n  - b\n---\nB"),
            ("---\nTags: [a]\n---\nB", "---\nTags:\n  - a\n  - b\n---\nB"),
            ("---\nTAGS:\n  - a\n---\nB", "---\nTAGS:\n  - a\n  - b\n---\nB"),
            ('---\n"tags": [a]\n---\nB', '---\n"tags":\n  - a\n  - b\n---\nB'),
            ("B", "---\ntags:\n  - b\n---\nB"),
            ("", "---\ntags:\n  - b\n---\n"),
            ("---\r\ntags: [a]\r\n---\r\nB\r\n", "---\r\ntags:\r\n  - a\r\n  - b\r\n---\r\nB\r\n"),
            ("\ufeff---\r\ntitle: x\r\n---\r\nB", "\ufeff---\r\ntitle: x\r\ntags:\r\n  - b\r\n---\r\nB"),
            ("\ufeffB\r\nC", "\ufeff---\r\ntags:\r\n  - b\r\n---\r\nB\r\nC"),
            ("---\ntags: [a]\n---", "---\ntags:\n  - a\n  - b\n---"),
        ],
    )  # fmt: skip
    async def test_the_tags_entry_is_replaced_by_a_block_list(
        self, vault, disk, sandbox: Sandbox, before, after
    ):
        path = await vault.write_note(sandbox.path("t.md"), before)
        await vault.update_tags(path, add=["b"])
        assert disk(path) == after.encode()

    @pytest.mark.parametrize(
        ("value", "kept"),
        [
            ('"a, #b"', ["a", "b"]),  # one quoted string: both tags survive
            ("'x #y'", ["x", "y"]),
            ('["a, #b", c]', ["a, #b", "c"]),  # a quoted item keeps its comma
            ("[a, 'b c']  # trailing comment", ["a", "b c"]),
        ],
    )
    async def test_quoted_and_commented_values_are_never_mangled(
        self, vault, disk, sandbox: Sandbox, value, kept
    ):
        original = f"---\ntags: {value}\ntitle: T\n---\nB\n"
        path = await vault.write_note(sandbox.path("q.md"), original)
        change = await vault.update_tags(path, add=["new"])
        text = disk(path).decode()
        assert change.tags == [*kept, "new"]
        assert (await vault.read_note(path)).frontmatter["tags"] == [*kept, "new"]
        assert text.endswith("\ntitle: T\n---\nB\n") and text.count("tags") == 1

    @pytest.mark.parametrize(
        "original",
        [
            "---\ntitle: A\ntags:\n  - a\ntitle: B\n---\nbody\n",  # duplicate key
            "---\ntags: [a\nk: : v\n---\nbody\n",  # invalid YAML
            "---\ntags: [#a, b]\ntitle: T\n---\nB\n",  # `#` starts a comment: the list never closes
            "\ufeff---\r\ntitle: A\r\ntitle: B\r\n---\r\nbody",
            "---\nplain text\n---\nbody\n",  # not a list of properties
        ],
    )
    async def test_frontmatter_obsidian_cannot_read_is_refused_not_shadowed(
        self, vault, disk, sandbox: Sandbox, original
    ):
        """A second block on top would turn the unreadable one into body text and hide its tags."""
        path = await vault.write_note(sandbox.path("bad.md"), original)
        with pytest.raises(InvalidArgumentError, match="fix it in Obsidian"):
            await vault.update_tags(path, add=["new"])
        with pytest.raises(InvalidArgumentError, match="fix it in Obsidian"):
            await vault.update_tags(path, remove=["a"])
        assert disk(path).decode() == original

    @pytest.mark.parametrize(
        ("before", "after"),
        [
            ("---\n---\nB", "---\ntags:\n  - b\n---\nB"),
            ("---\r\n---\r\nB", "---\r\ntags:\r\n  - b\r\n---\r\nB"),
            ("---\n# a comment\n\n---\nB", "---\n# a comment\n\ntags:\n  - b\n---\nB"),
            ("---\n---", "---\ntags:\n  - b\n---"),
        ],
    )
    async def test_an_empty_or_comment_only_block_gets_the_tags_inside_it(
        self, vault, disk, sandbox: Sandbox, before, after
    ):
        path = await vault.write_note(sandbox.path("empty.md"), before)
        await vault.update_tags(path, add=["b"])
        assert disk(path) == after.encode()
        assert (await vault.read_note(path)).frontmatter["tags"] == ["b"]

    async def test_a_binary_file_is_refused_and_its_bytes_are_never_rewritten(
        self, vault, cli, disk, sandbox: Sandbox
    ):
        path = sandbox.path("pic.md")
        await put(cli, path, BINARY)
        with pytest.raises(InvalidArgumentError, match="not a text file"):
            await vault.update_tags(path, add=["new"])
        assert disk(path) == BINARY

    async def test_add_and_remove_are_case_insensitive_and_normalised(
        self, vault, disk, sandbox: Sandbox
    ):
        path = await vault.write_note(sandbox.path("t.md"), "---\ntags: [Alpha, beta]\n---\nB")
        change = await vault.update_tags(path, add=["ALPHA", "#Gamma", "gamma"], remove=["#BETA"])
        assert (change.tags, change.added, change.removed) == (
            ["Alpha", "Gamma"],
            ["Gamma"],
            ["beta"],
        )
        assert disk(path) == b"---\ntags:\n  - Alpha\n  - Gamma\n---\nB"
        await vault.update_tags(path, remove=["alpha", "gamma"])
        assert disk(path) == b"---\ntags: []\n---\nB"
        assert (await vault.read_note(path)).tags == []

    async def test_a_tag_that_needs_quoting_is_quoted(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(sandbox.path("t.md"), "B")
        await vault.update_tags(path, add=["no", "2024-plan", "a/b", "été"])
        assert (
            disk(path).decode() == '---\ntags:\n  - "no"\n  - "2024-plan"\n  - a/b\n  - été\n---\nB'
        )
        assert (await vault.read_note(path)).frontmatter["tags"] == [
            "no",
            "2024-plan",
            "a/b",
            "été",
        ]

    async def test_body_that_starts_with_a_horizontal_rule_is_untouched(
        self, vault, disk, sandbox: Sandbox
    ):
        body = "---\ntags: [a]\n---\n---\n\nrule above\n\n---\nend\n"
        path = await vault.write_note(sandbox.path("hr_after_fm.md"), body)
        await vault.update_tags(path, add=["new"])
        assert disk(path).decode() == body.replace("tags: [a]", "tags:\n  - a\n  - new")
        for name, rule in {
            "hr": "---\n\nHello\n\n---\n\nWorld\n",
            "hr_text": "---\nx\n---\ny\n",
        }.items():
            path = await vault.write_note(sandbox.path(f"{name}.md"), rule)
            with pytest.raises(InvalidArgumentError, match="fix it in Obsidian"):
                await vault.update_tags(path, add=["new"])  # Obsidian reads it as a property block
            assert disk(path).decode() == rule

    async def test_body_is_byte_identical(self, vault, disk, sandbox: Sandbox):
        body = (
            "# H\r\n\r\n```yaml\r\n---\r\nkey: value\r\n---\r\n```\r\n$\\theta$ \\n \\t \u2028 end"
        )
        original = "\ufeff---\r\n# c\r\nb: 2\r\na: 1\r\ntags: [x]\r\nz: 3\r\n---\r\n" + body
        path = await vault.write_note(sandbox.path("b.md"), original)
        await vault.update_tags(path, add=["yy"])
        expected = "\ufeff---\r\n# c\r\nb: 2\r\na: 1\r\ntags:\r\n  - x\r\n  - yy\r\nz: 3\r\n---\r\n"
        assert disk(path) == (expected + body).encode()

    async def test_a_block_the_old_editor_could_not_read_is_edited_in_place(
        self, vault, disk, sandbox: Sandbox
    ):
        """Obsidian says where the block is, so odd keys never cause a second block."""
        odd = '---\nfoo:bar: baz\n"quoted: key": 1\ntitle: T\ntags: [x]\n---\nBody'
        path = await vault.write_note(sandbox.path("odd.md"), odd)
        await vault.update_tags(path, add=["new"])
        assert disk(path).decode() == odd.replace("tags: [x]", "tags:\n  - x\n  - new")
        bare = "---\nfoo:bar: baz\n---\nBody"
        path = await vault.write_note(sandbox.path("bare.md"), bare)
        await vault.update_tags(path, add=["new"])
        assert disk(path).decode() == "---\nfoo:bar: baz\ntags:\n  - new\n---\nBody"

    async def test_only_the_first_tags_key_is_edited_like_obsidian_reads_it(
        self, vault, disk, sandbox: Sandbox
    ):
        path = await vault.write_note(sandbox.path("two.md"), "---\nTags: [x]\ntags: [y]\n---\nB")
        change = await vault.update_tags(path, add=["new"])
        assert change.tags == ["x", "new"]  # `Tags` wins in Obsidian: `tags: [y]` is not tags
        assert disk(path).decode() == "---\nTags:\n  - x\n  - new\ntags: [y]\n---\nB"

    async def test_ten_concurrent_edits_lose_nothing(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(sandbox.path("c.md"), "---\ntags: [base]\n---\nBody\n")
        await asyncio.gather(*(vault.update_tags(path, add=[f"t{i}"]) for i in range(10)))
        tags = (await vault.read_note(path)).frontmatter["tags"]
        assert sorted(tags) == sorted(["base", *(f"t{i}" for i in range(10))])
        assert disk(path).endswith(b"---\nBody\n")

    async def test_concurrent_edits_on_a_bom_crlf_file(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(
            sandbox.path("c.md"), "\ufeff---\r\ntitle: T\r\n---\r\nBody\r\n"
        )
        await asyncio.gather(*(vault.update_tags(path, add=[f"k{i}"]) for i in range(6)))
        raw = disk(path)
        assert raw.startswith("\ufeff---\r\ntitle: T\r\n".encode())
        assert raw.endswith(b"\r\n---\r\nBody\r\n")
        assert raw.count(b"\n") == raw.count(b"\r\n")  # no stray LF-only lines
        assert sorted((await vault.read_note(path)).frontmatter["tags"]) == [
            f"k{i}" for i in range(6)
        ]

    async def test_eight_heading_appends_and_ten_tag_edits_on_one_note(
        self, vault, disk, sandbox: Sandbox
    ):
        """Concurrent writers to ONE note neither stall on Obsidian's re-parse nor lose updates."""
        path = await vault.write_note(
            sandbox.path("c.md"), "---\ntags: [base]\n---\n# T\n\n## S\n\nold\n\n## Z\n\nz\n"
        )
        started = time.monotonic()
        await asyncio.gather(
            *(vault.append(path, f"h{i}", heading="## S") for i in range(8)),
            *(vault.update_tags(path, add=[f"t{i}"]) for i in range(10)),
        )
        assert time.monotonic() - started < 10
        note = await vault.read_note(path)
        assert sorted(note.frontmatter["tags"]) == sorted(["base", *(f"t{i}" for i in range(10))])
        section = note.content.split("## S\n")[1].split("\n\n## Z")[0].split("\n")
        assert section[:2] == ["", "old"]
        assert sorted(section[2:]) == sorted(f"h{i}" for i in range(8))
        assert note.content.endswith("\n\n## Z\n\nz\n") and note.headings == ["T", "S", "Z"]

    @pytest.mark.parametrize("tag", ["", "   ", "#", "a b", "12345", "a,b", "a#b", "x[y]"])
    async def test_invalid_tags_are_rejected_before_anything_is_written(
        self, vault, disk, sandbox: Sandbox, tag
    ):
        path = await vault.write_note(sandbox.path("t.md"), YAML_NOTE)
        with pytest.raises(InvalidArgumentError, match="Invalid tag"):
            await vault.update_tags(path, add=[tag])
        with pytest.raises(InvalidArgumentError, match="Invalid tag"):
            await vault.update_tags(path, remove=[tag])
        assert disk(path).decode() == YAML_NOTE

    async def test_contradictory_requests_are_rejected(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(sandbox.path("t.md"), YAML_NOTE)
        with pytest.raises(InvalidArgumentError, match="at least one"):
            await vault.update_tags(path)
        with pytest.raises(InvalidArgumentError, match="both"):
            await vault.update_tags(path, add=["x"], remove=["#X"])
        assert disk(path).decode() == YAML_NOTE

    async def test_unsupported_shapes_are_refused_not_mangled(self, vault, disk, sandbox: Sandbox):
        for name, weird in {
            "map": "---\ntags:\n  nested: map\n---\nB\n",
            "objects": "---\ntags: [{a: 1}]\n---\nB\n",
            "number": "---\ntags: 5\n---\nB\n",
        }.items():
            path = await vault.write_note(sandbox.path(f"{name}.md"), weird)
            with pytest.raises(InvalidArgumentError, match="not a list"):
                await vault.update_tags(path, add=["x"])
            assert disk(path).decode() == weird

    async def test_missing_and_non_markdown_files(self, vault, cli, sandbox: Sandbox):
        with pytest.raises(NoteNotFoundError):
            await vault.update_tags(sandbox.path("nope.md"), add=["x"])
        await put(cli, sandbox.path("a.txt"), "text")
        with pytest.raises(InvalidArgumentError, match="markdown"):
            await vault.update_tags(sandbox.path("a.txt"), add=["x"])


class TestReplaceBody:
    async def test_only_the_body_and_the_given_properties_change(
        self, vault, disk, sandbox: Sandbox
    ):
        original = "\ufeff---\r\n# c\r\nzip: 01234\r\ntype: old\r\nver: 1.10\r\n---\r\n\r\nold\r\n"
        path = await vault.write_note(sandbox.path("n.md"), original)
        await vault.replace_body(
            path,
            "new",
            properties={"type": "new", "updated": "2026-01-02T03:04:05Z"},
            defaults={"created": "kept", "ver": "ignored"},
        )
        assert (
            disk(path)
            == (
                "\ufeff---\r\n# c\r\nzip: 01234\r\ntype: new\r\nver: 1.10\r\ncreated: kept\r\n"
                "updated: '2026-01-02T03:04:05Z'\r\n---\r\n\r\nnew"
            ).encode()
        )
        await vault.replace_body(path, "again", properties={"updated": "later"})
        assert disk(path).decode().endswith("updated: later\r\n---\r\n\r\nagain")

    async def test_a_multi_line_entry_is_replaced_whole_and_a_block_is_created_when_missing(
        self, vault, disk, sandbox: Sandbox
    ):
        path = await vault.write_note(
            sandbox.path("m.md"), "---\ntype:\n  - a\n  - b\nkeep: 1\n---\nold"
        )
        await vault.replace_body(path, "new", properties={"type": "x y"})
        assert disk(path) == b"---\ntype: x y\nkeep: 1\n---\nnew"
        bare = await vault.write_note(sandbox.path("b.md"), "just text\n")
        await vault.replace_body(bare, "new\n", defaults={"created": "c"}, properties={"u": 1})
        assert disk(bare) == b"---\ncreated: c\nu: 1\n---\n\nnew\n"

    async def test_a_property_that_is_not_a_plain_key_line_is_refused_or_left_alone(
        self, vault, disk, sandbox: Sandbox
    ):
        flow = "---\n{type: old}\n---\nbody"
        path = await vault.write_note(sandbox.path("f.md"), flow)
        with pytest.raises(InvalidArgumentError, match="plain key"):
            await vault.replace_body(path, "new", properties={"type": "x"})
        assert disk(path).decode() == flow
        await vault.replace_body(path, "new", defaults={"type": "x"})  # present: not a default
        assert disk(path).decode() == "---\n{type: old}\n---\nnew"

    async def test_refusals_leave_the_file_untouched(self, vault, cli, disk, sandbox: Sandbox):
        bad = "---\ntitle: A\ntitle: B\n---\nbody"
        path = await vault.write_note(sandbox.path("bad.md"), bad)
        with pytest.raises(InvalidArgumentError, match="cannot parse"):
            await vault.replace_body(path, "new", properties={"updated": "x"})
        assert disk(path).decode() == bad
        await put(cli, sandbox.path("pic.md"), BINARY)
        with pytest.raises(InvalidArgumentError, match="not a text file"):
            await vault.replace_body(sandbox.path("pic.md"), "new")
        assert disk(sandbox.path("pic.md")) == BINARY
        await put(cli, sandbox.path("a.txt"), "text")
        with pytest.raises(InvalidArgumentError, match="markdown"):
            await vault.replace_body(sandbox.path("a.txt"), "new")
        with pytest.raises(InvalidArgumentError, match="property name"):
            await vault.replace_body(path, "new", properties={"a: b": 1})
        with pytest.raises(NoteNotFoundError):
            await vault.replace_body(sandbox.path("nope.md"), "new")

    async def test_concurrent_body_and_tag_edits_lose_nothing(self, vault, disk, sandbox: Sandbox):
        path = await vault.write_note(sandbox.path("c.md"), "---\ntags: [base]\n---\n\nbody\n")
        await asyncio.gather(
            *(vault.replace_body(path, f"body {i}", properties={"n": i}) for i in range(3)),
            *(vault.update_tags(path, add=[f"t{i}"]) for i in range(6)),
        )
        note = await vault.read_note(path)
        assert sorted(note.frontmatter["tags"]) == sorted(["base", *(f"t{i}" for i in range(6))])
        assert note.content.count("\nn:") == 1 and note.frontmatter["n"] in {0, 1, 2}
        assert note.content.rsplit("---\n\n", 1)[1] in {"body 0", "body 1", "body 2"}


# ---------------------------------------------------------------------------
# links, backlinks, link text
# ---------------------------------------------------------------------------


async def cli_backlinks(cli: ObsidianCLI, path: str) -> dict[str, int]:
    output = (await cli.run("backlinks", f"path={path}", "counts", "format=json")).strip()
    rows = json.loads(output) if output.startswith("[") else []  # "No backlinks found." otherwise
    return {row["file"]: int(row["count"]) for row in rows}


class TestLinks:
    async def build(self, vault: Vault, sb: Sandbox) -> dict[str, str]:
        w = vault.write_note
        p = {
            "target": await w(sb.path("Target.md"), "# Target\n\n## Sec\n\ntext ^blk1\n"),
            "dup_a": await w(sb.path("Dup/Twin.md"), "twin in Dup"),
            "dup_b": await w(sb.path("Other/Twin.md"), "twin in Other"),
            "src": await w(
                sb.path("Src.md"),
                "---\nrel: '[[Target]]'\nrels: ['[[Target]]', '[[Dup/Twin]]']\n---\n"
                "Heading [[Target#Sec]] and alias [[Target#Sec|shown]] and block [[Target#^blk1]]\n"
                "Embed ![[Target]] and md [link](Target.md) and same-note [[#Mine]] and self [[Src]]\n"
                "Dup [[Twin]] full [[Dup/Twin]] other [[Other/Twin]] missing [[Nowhere]] url [x](https://e.com)\n"
                "\n# Mine\n",
            ),
            "plain": await w(sb.path("Plain.md"), "links to [[Target]] once\n"),
        }
        return p

    async def test_outgoing_links_kinds_targets_and_display(self, vault, sandbox: Sandbox):
        p = await self.build(vault, sandbox)
        links = await vault.outgoing_links(p["src"])
        as_tuples = [(x.kind, x.link, x.target) for x in links]
        target = p["target"]
        assert ("link", "Target#Sec", target) in as_tuples
        assert ("link", "Target#^blk1", target) in as_tuples
        assert ("link", "Target.md", target) in as_tuples
        assert ("link", "#Mine", p["src"]) in as_tuples
        assert ("link", "Src", p["src"]) in as_tuples
        assert ("link", "Dup/Twin", p["dup_a"]) in as_tuples
        assert ("link", "Other/Twin", p["dup_b"]) in as_tuples
        assert ("link", "Nowhere", None) in as_tuples
        assert ("embed", "Target", target) in as_tuples
        assert ("frontmatter", "Target", target) in as_tuples
        assert ("frontmatter", "Dup/Twin", p["dup_a"]) in as_tuples
        assert not any(x.link.startswith("https") for x in links)
        alias = next(x for x in links if x.link == "Target#Sec" and x.display == "shown")
        assert alias.kind == "link"
        with pytest.raises(NoteNotFoundError):
            await vault.outgoing_links(sandbox.path("missing.md"))

    async def test_backlinks_match_obsidian_cli(self, vault, cli, sandbox: Sandbox):
        p = await self.build(vault, sandbox)
        # `vault.backlinks` is consistent at once; the CLI answers from Obsidian's own link
        # index, which catches up a few ms after the last write, so the CLI side is awaited.
        for key in ("target", "dup_a", "dup_b", "src", "plain"):
            ours = await vault.backlinks(p[key])

            async def same(path: str = p[key], expected: list[str] = ours) -> None:
                assert expected == sorted(await cli_backlinks(cli, path))

            await eventually(same)
        # Src links to Target by property, heading, alias, block, embed and markdown link
        assert await vault.backlinks(p["target"]) == sorted([p["src"], p["plain"]])
        assert p["src"] in await vault.backlinks(p["src"])  # self links count, like Obsidian
        assert await vault.backlinks(p["dup_b"]) == [p["src"]]

    async def test_backlinks_of_a_note_written_a_moment_ago(self, vault, sandbox: Sandbox):
        target = await vault.write_note(sandbox.path("T.md"), "t")
        await vault.write_note(sandbox.path("S.md"), "[[T]]")
        assert await vault.backlinks(target) == [sandbox.path("S.md")]  # no waiting

    async def test_backlinks_follow_edits_and_deletes(self, vault, sandbox: Sandbox):
        target = await vault.write_note(sandbox.path("T.md"), "t")
        source = await vault.write_note(sandbox.path("S.md"), "no link yet")
        assert await vault.backlinks(target) == []
        await vault.append(source, "now [[T]]")
        assert await vault.backlinks(target) == [source]
        await vault.delete(source, permanent=True)
        assert await vault.backlinks(target) == []

    async def test_backlinks_missing_note(self, vault, sandbox: Sandbox):
        with pytest.raises(NoteNotFoundError):
            await vault.backlinks(sandbox.path("missing.md"))

    async def test_resolve_link_and_link_text(self, vault, sandbox: Sandbox):
        p = await self.build(vault, sandbox)
        src = p["src"]
        assert await vault.resolve_link("Target", src) == p["target"]
        assert await vault.resolve_link("target", src) == p["target"]  # case-insensitive
        assert await vault.resolve_link("Target#Sec", src) == p["target"]
        assert await vault.resolve_link("Target|alias", src) == p["target"]
        assert await vault.resolve_link(sandbox.path("Target.md"), src) == p["target"]
        assert await vault.resolve_link("Dup/Twin", src) == p["dup_a"]
        with pytest.raises(NoteNotFoundError, match="No note matches"):
            await vault.resolve_link("Nowhere", src)
        with pytest.raises(InvalidArgumentError):
            await vault.resolve_link("  ", src)
        assert await vault.link_text(p["target"], src) == "Target"
        # two notes called Twin: the link text must disambiguate with a path
        text_a = await vault.link_text(p["dup_a"], src)
        text_b = await vault.link_text(p["dup_b"], src)
        assert text_a != text_b and "/" in text_a and "/" in text_b
        assert await vault.resolve_link(text_a, src) == p["dup_a"]
        assert await vault.resolve_link(text_b, src) == p["dup_b"]


class TestAppendUnlessLinked:
    async def notes(self, vault: Vault, sb: Sandbox) -> tuple[str, str]:
        target = await vault.write_note(sb.path("Alpha.md"), "# Alpha\n")
        source = await vault.write_note(sb.path("Src.md"), "# Src\n\n## See\n\nold\n\n## End\n")
        return source, target

    async def test_eight_concurrent_calls_add_one_line_and_report_one_add(
        self, vault, disk, sandbox: Sandbox
    ):
        source, target = await self.notes(vault, sandbox)
        results = await asyncio.gather(
            *(vault.append_unless_linked(source, target, "- [[Alpha]]") for _ in range(8))
        )
        assert sorted(results) == [False] * 7 + [True]
        assert disk(source).decode() == "# Src\n\n## See\n\nold\n\n## End\n- [[Alpha]]\n"

    async def test_under_a_heading_and_any_kind_of_existing_link_counts(
        self, vault, disk, sandbox: Sandbox
    ):
        source, target = await self.notes(vault, sandbox)
        assert await vault.append_unless_linked(source, target, "- [[Alpha]]", "See")
        assert disk(source).decode() == "# Src\n\n## See\n\nold\n- [[Alpha]]\n\n## End\n"
        for existing in ("![[Alpha]]", "text [[Alpha|alias]]", "---\nrel: '[[Alpha]]'\n---\nx"):
            note = await vault.write_note(sandbox.path("Other.md"), existing, overwrite=True)
            assert not await vault.append_unless_linked(note, target, "- [[Alpha]]")
            assert disk(note).decode() == existing
        with pytest.raises(HeadingNotFoundError):
            await vault.append_unless_linked(
                source, sandbox.path("Other.md"), "- [[Other]]", "Nope"
            )

    async def test_a_binary_or_missing_file_is_refused_and_untouched(
        self, vault, cli, disk, sandbox: Sandbox
    ):
        _, target = await self.notes(vault, sandbox)
        await put(cli, sandbox.path("pic.md"), BINARY)
        with pytest.raises(InvalidArgumentError, match="not a text file"):
            await vault.append_unless_linked(sandbox.path("pic.md"), target, "- [[Alpha]]")
        assert disk(sandbox.path("pic.md")) == BINARY
        with pytest.raises(NoteNotFoundError):
            await vault.append_unless_linked(sandbox.path("nope.md"), target, "- [[Alpha]]")


# ---------------------------------------------------------------------------
# tags
# ---------------------------------------------------------------------------


async def cli_tag_counts(cli: ObsidianCLI, path: str | None = None) -> dict[str, int]:
    args = ["tags", "counts", "format=json"] + ([f"path={path}"] if path else [])
    output = (await cli.run(*args)).strip()
    rows = json.loads(output) if output.startswith("[") else []  # "No tags found." otherwise
    return {row["tag"].removeprefix("#"): int(row["count"]) for row in rows}


class TestTags:
    async def build(self, vault: Vault, sb: Sandbox, uid: str) -> dict[str, str]:
        w = vault.write_note
        return {
            "a": await w(
                sb.path("A.md"),
                f"---\ntags: [fm{uid}, nest{uid}/child]\n---\nBody #inline{uid} #Inline{uid} #deep{uid}/er/tag\n"
                f"```\n#code{uid}\n```\n",
            ),
            "b": await w(
                sb.path("B.md"), f"---\ntags: FM{uid}\n---\n#nest{uid}/other and #inline{uid}\n"
            ),
            "c": await w(sb.path("C.md"), f"no tags here, issue #123 and a#{uid}anchor\n"),
        }

    async def test_note_tags_match_obsidian_cli(self, vault, cli, sandbox: Sandbox):
        uid = uuid.uuid4().hex[:6]
        p = await self.build(vault, sandbox, uid)
        for key in ("a", "b", "c"):
            ours = (await vault.read_note(p[key])).tags

            async def same(path: str = p[key], ours: list[str] = ours) -> None:
                theirs = list(await cli_tag_counts(cli, path))
                # the CLI lists #inline and #Inline separately for one note; Obsidian's tag pane merges them
                assert sorted({t.lower() for t in ours}) == sorted({t.lower() for t in theirs})

            await eventually(same)
        a = (await vault.read_note(p["a"])).tags
        assert {t.lower() for t in a} == {
            f"fm{uid}", f"nest{uid}/child", f"inline{uid}", f"deep{uid}/er/tag"
        }  # fmt: skip
        assert len(a) == len({t.lower() for t in a})  # #inline / #Inline deduped like Obsidian

    async def test_vault_tag_counts_match_obsidian_cli(self, vault, cli, sandbox: Sandbox):
        uid = uuid.uuid4().hex[:6]
        await self.build(vault, sandbox, uid)
        ours = {t: n for t, n in (await vault.tags()).items() if uid in t.lower()}

        async def same() -> None:
            theirs = {t: n for t, n in (await cli_tag_counts(cli)).items() if uid in t.lower()}
            assert ours == theirs

        await eventually(same)
        by_lower = {t.lower(): n for t, n in ours.items()}
        assert (
            by_lower[f"inline{uid}"] == 3
        )  # #inline, #Inline, and B's #inline: one tag, case-insensitively
        assert by_lower[f"nest{uid}"] == 2  # parents count their children's notes' tags
        assert (
            by_lower[f"nest{uid}/child"] == 1
            and by_lower[f"deep{uid}/er"] == 1
            and f"code{uid}" not in by_lower
        )

    async def test_notes_with_tag(self, vault, sandbox: Sandbox):
        uid = uuid.uuid4().hex[:6]
        p = await self.build(vault, sandbox, uid)
        assert await vault.notes_with_tag(f"inline{uid}") == sorted([p["a"], p["b"]])
        assert await vault.notes_with_tag(f"#INLINE{uid}") == sorted([p["a"], p["b"]])
        assert await vault.notes_with_tag(f"nest{uid}") == sorted([p["a"], p["b"]])
        assert await vault.notes_with_tag(f"nest{uid}", include_nested=False) == []
        assert await vault.notes_with_tag(f"nest{uid}/other") == [p["b"]]
        assert await vault.notes_with_tag(f"fm{uid}") == sorted([p["a"], p["b"]])
        assert await vault.notes_with_tag(f"code{uid}") == []
        with pytest.raises(InvalidArgumentError):
            await vault.notes_with_tag("a b")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


class TestSearch:
    async def test_limit_truncation_and_dedupe(self, vault, sandbox: Sandbox):
        token = f"zqx{uuid.uuid4().hex[:10]}"
        for i in range(5):
            await vault.write_note(
                sandbox.path(f"n{i}.md"), f"first {token} {token} twice\nnothing\nthird {token}\n"
            )

        async def five_hits() -> None:
            assert len((await vault.search(token, folder=sandbox.dir, limit=10)).hits) == 5

        await eventually(five_hits)
        all_hits = await vault.search(token, folder=sandbox.dir, limit=10)
        assert all_hits.truncated is False
        for hit in all_hits.hits:
            assert [(m.line, m.text.strip()) for m in hit.matches] == [
                (1, f"first {token} {token} twice"),
                (3, f"third {token}"),
            ]  # one entry per line, not per occurrence
        limited = await vault.search(token, folder=sandbox.dir, limit=3)
        assert len(limited.hits) == 3 and limited.truncated is True
        exact = await vault.search(token, folder=sandbox.dir, limit=5)
        assert len(exact.hits) == 5 and exact.truncated is False

    async def test_folder_scope_and_no_match(self, vault, sandbox: Sandbox):
        token = f"zqx{uuid.uuid4().hex[:10]}"
        await vault.write_note(sandbox.path("in/a.md"), token)
        await vault.write_note(sandbox.path("out/b.md"), token)

        async def found() -> None:
            assert {h.path for h in (await vault.search(token, folder=sandbox.dir)).hits} == {
                sandbox.path("in/a.md"),
                sandbox.path("out/b.md"),
            }

        await eventually(found)
        scoped = await vault.search(token, folder=sandbox.path("in") + "/")
        assert [h.path for h in scoped.hits] == [sandbox.path("in/a.md")]
        nothing = await vault.search(f"nomatch{uuid.uuid4().hex}", folder=sandbox.dir)
        assert nothing.hits == [] and nothing.truncated is False

    async def test_invalid_arguments(self, vault):
        with pytest.raises(InvalidArgumentError):
            await vault.search("   ")
        with pytest.raises(InvalidArgumentError):
            await vault.search("x", limit=0)
        with pytest.raises(InvalidArgumentError):
            await vault.search("x", folder="../outside")

    async def test_a_long_line_is_cut_around_the_match(self, vault, sandbox: Sandbox):
        token = f"zqx{uuid.uuid4().hex[:10]}"
        await vault.write_note(
            sandbox.path("long.md"),
            f"{'a' * 1000} {token} {'b' * 1000}\n{token} at the start {'c' * 1000}\nshort {token}\n",
        )

        async def indexed() -> None:
            assert (await vault.search(token, folder=sandbox.dir)).hits

        await eventually(indexed)
        (hit,) = (await vault.search(token, folder=sandbox.dir)).hits
        middle, start, short = (m.text for m in hit.matches)
        assert token in middle and middle.startswith("…") and middle.endswith("…")
        assert len(middle) <= 302
        assert token in start and not start.startswith("…") and start.endswith("…")
        assert len(start) <= 301
        assert short == f"short {token}"  # short lines are returned whole


# ---------------------------------------------------------------------------
# daily notes
# ---------------------------------------------------------------------------


class TestDaily:
    PAST = date(2020, 3, 5)

    async def test_path_follows_folder_and_format_for_any_date(self, vault, daily_config):
        folder = daily_config["folder"]
        assert await vault.daily_path(self.PAST) == f"{folder}/2020/03/2020-03-05.md"
        assert await vault.daily_path(date(1999, 12, 31)) == f"{folder}/1999/12/1999-12-31.md"

    async def test_default_options_use_iso_date_in_the_vault_root(self, vault, cli):
        original = await cli.eval(
            "const o = app.internalPlugins.getPluginById('daily-notes').instance; globalThis.__brainSaved = o.options; o.options = {}; return null;"
        )
        try:
            assert await vault.daily_path(self.PAST) == "2020-03-05.md"
        finally:
            await cli.eval(
                "app.internalPlugins.getPluginById('daily-notes').instance.options = globalThis.__brainSaved; delete globalThis.__brainSaved; return null;"
            )
        assert original is None

    async def test_read_never_creates(self, vault, daily_config):
        assert await vault.read_daily(self.PAST) is None
        assert not await exists(vault, await vault.daily_path(self.PAST))

    async def test_append_creates_a_past_date_from_the_template_then_appends(
        self, vault, disk, daily_config
    ):
        path = await vault.append_daily("- first entry $\\theta$ \\n", self.PAST)
        assert path == f"{daily_config['folder']}/2020/03/2020-03-05.md"
        text = disk(path).decode()
        assert text.startswith(
            "# 2020-03-05\ndate=2020-03-05 fmt=Thursday, March 5 2020 year=2020 time="
        )
        assert " untouched={{foo}}\n" in text and "## Log\n" in text
        assert text.endswith("## Log\n- first entry $\\theta$ \\n")
        assert "t2={{ time }}" not in text  # {{ time }} with spaces is still the time variable
        assert (await vault.read_daily(self.PAST)).content == text
        await vault.append_daily("- second", self.PAST)
        assert disk(path).decode() == text + "\n- second"
        assert not await exists(vault, f"{daily_config['folder']}/2026")  # today's was not created

    async def test_append_under_a_heading(self, vault, disk, daily_config):
        path = await vault.append_daily("- under log", self.PAST, heading="## Log")
        assert disk(path).decode().endswith("## Log\n- under log\n")  # the template's newline stays

    async def test_a_missing_heading_is_created_in_the_same_edit(self, vault, disk, daily_config):
        path = await vault.append_daily("- first", self.PAST, heading="Notes")
        assert disk(path).decode().endswith("## Log\n\n## Notes\n\n- first")
        await vault.append_daily("- second", self.PAST, heading="notes")
        text = disk(path).decode()
        assert text.endswith("## Notes\n\n- first\n- second") and text.count("## Notes") == 1
        await vault.append_daily("- deep", self.PAST, heading="### Deep dive")
        assert (
            disk(path).decode().endswith("## Notes\n\n- first\n- second\n\n### Deep dive\n\n- deep")
        )

    async def test_concurrent_entries_under_a_missing_heading_make_one_section(
        self, vault, disk, daily_config
    ):
        day = date(2021, 8, 9)
        await asyncio.gather(
            *(vault.append_daily(f"- r{i}", day, heading="Race") for i in range(4))
        )
        text = disk(await vault.daily_path(day)).decode()
        assert text.count("## Race") == 1
        assert sorted(text.split("## Race\n\n")[1].split("\n")) == [f"- r{i}" for i in range(4)]

    async def test_concurrent_appends_to_a_missing_daily_note(self, vault, disk, daily_config):
        day = date(2021, 7, 9)
        await asyncio.gather(*(vault.append_daily(f"- e{i}", day) for i in range(6)))
        path = await vault.daily_path(day)
        entries = [line for line in disk(path).decode().split("\n") if line.startswith("- e")]
        assert sorted(entries) == sorted(f"- e{i}" for i in range(6))

    async def test_missing_template_gives_an_empty_note(self, vault, cli, disk, daily_config):
        await vault.delete(
            f"{daily_config['folder'].rsplit('/', 1)[0]}/Templates/Daily.md", permanent=True
        )
        path = await vault.append_daily("only", date(2022, 1, 2))
        assert disk(path) == b"only"


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


class TestSnapshot:
    async def test_snapshot_lists_notes_files_and_folders(self, vault, cli, sandbox: Sandbox):
        await vault.write_note(
            sandbox.path("one.md"), "---\ntitle: One\ntags: [fm]\n---\n# Head\n[[two]] #inline\n"
        )
        await vault.write_note(sandbox.path("sub/two.md"), "two")
        await put(cli, sandbox.path("sub/pic.png"), b"\x89PNG")
        snap = await vault.snapshot(sandbox.dir)
        assert [n.path for n in snap.notes] == [sandbox.path("one.md"), sandbox.path("sub/two.md")]
        one = snap.notes[0]
        assert one.frontmatter == {"title": "One", "tags": ["fm"]}
        assert sorted(one.tags) == ["fm", "inline"] and one.headings == ["Head"]
        assert [(x.link, x.target, x.kind) for x in one.links] == [
            ("two", sandbox.path("sub/two.md"), "link")
        ]
        assert one.size == len(b"---\ntitle: One\ntags: [fm]\n---\n# Head\n[[two]] #inline\n")
        assert snap.folders == [sandbox.path("sub")]  # the folder itself is not listed

    async def test_snapshot_of_a_missing_folder_is_empty_and_whole_vault_works(
        self, vault, sandbox: Sandbox
    ):
        empty = await vault.snapshot(sandbox.path("nope"))
        assert (empty.notes, empty.folders) == ([], [])
        await vault.write_note(sandbox.path("x.md"), "x")
        whole = await vault.snapshot()
        assert sandbox.path("x.md") in {n.path for n in whole.notes}
        assert sandbox.dir in whole.folders
