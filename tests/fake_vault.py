"""The one in-memory stand-in for `Vault`: files are plain text, metadata is parsed like Obsidian.

Frontmatter comes from the file's own `---` block, `#tags` and `[[wikilinks]]` from its text.
Every `Vault` method the tools and resources call is here; `calls` records one entry per call
(to assert "one eval") and `writes` / `trashed` record what changed.
"""

import json
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import PurePosixPath
from typing import Any

import yaml

from obsidian_brain.exceptions import (
    HeadingNotFoundError,
    InvalidArgumentError,
    NoteExistsError,
    NoteNotFoundError,
)
from obsidian_brain.memory import frontmatter_yaml, split_frontmatter
from obsidian_brain.models import (
    FileInfo,
    Link,
    Note,
    NoteSnapshot,
    SearchHit,
    SearchMatch,
    SearchResults,
    TagChange,
    VaultSnapshot,
)

NOW = datetime(2026, 11, 23, 3, 24, 12, tzinfo=UTC)
_INLINE_TAG = re.compile(r"(?<![\w/])#([A-Za-z][\w/-]*)")
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)  # Obsidian reads no tags inside code
_CODE_SPAN = re.compile(r"`[^`\n]*`")
_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_TAGS_ENTRY = re.compile(r"^(tags|tag):")


def _prefix(folder: str) -> str:
    folder = folder.strip("/")
    return f"{folder}/" if folder else ""


def _dedupe(tags: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for tag in tags:
        seen.setdefault(tag.lower(), tag)
    return list(seen.values())


class FakeVault:
    def __init__(self, files: dict[str, str] | None = None, extra_folders: list[str] | None = None):
        self.files: dict[str, str] = dict(files or {})
        self.extra_folders = list(extra_folders or [])
        self.trashed: list[str] = []
        self.deleted: list[str] = []  # removed for good (`permanent=True`)
        self.writes: list[str] = []
        self.calls: list[str] = []  # one entry per Vault method call, to assert "one eval"
        self.daily_folder = "Daily"

    # -- parsing -------------------------------------------------------------------------

    def _frontmatter(self, text: str) -> dict[str, Any]:
        block = split_frontmatter(text)[0]
        try:
            loaded = (
                yaml.safe_load("".join(block.splitlines(keepends=True)[1:-1])) if block else None
            )
        except yaml.YAMLError:  # Obsidian shows no properties for frontmatter it cannot parse
            loaded = None
        loaded = loaded if isinstance(loaded, dict) else {}
        return json.loads(json.dumps(loaded, default=str))  # type: ignore[no-any-return]

    @staticmethod
    def _fm_tags(fm: dict[str, Any]) -> list[str]:
        raw = fm.get("tags", fm.get("tag")) or []
        raw = raw.replace(",", " ").split() if isinstance(raw, str) else raw
        return [str(t).removeprefix("#") for t in raw]

    def _tag_uses(self, text: str) -> list[str]:
        """Every tag occurrence: frontmatter entries plus each inline use outside code."""
        body = _CODE_SPAN.sub("", _CODE_FENCE.sub("", split_frontmatter(text)[1]))
        return [*self._fm_tags(self._frontmatter(text)), *_INLINE_TAG.findall(body)]

    def _links(self, text: str) -> list[Link]:
        stems = {PurePosixPath(p).stem: p for p in self.files if p.endswith(".md")}
        return [
            Link(
                target=stems.get(name.strip()),
                link=name.strip(),
                display=alias or None,
                kind="link",
            )
            for name, alias in _WIKILINK.findall(split_frontmatter(text)[1])
        ]

    def _snapshot_note(self, path: str) -> NoteSnapshot:
        text = self.files[path]
        return NoteSnapshot(
            path=path,
            size=len(text.encode()),
            modified=NOW,
            frontmatter=self._frontmatter(text),
            tags=_dedupe(self._tag_uses(text)),
            links=self._links(text),
            headings=re.findall(r"(?m)^#{1,6}\s+(.*)$", split_frontmatter(text)[1]),
        )

    def _info(self, path: str) -> FileInfo:
        return FileInfo(
            path=path,
            extension=PurePosixPath(path).suffix.lstrip("."),
            size=len(self.files[path].encode()),
            modified=NOW,
        )

    def _folders(self) -> list[str]:
        folders: set[str] = set()
        for path in [*self.files, *(f"{f}/" for f in self.extra_folders)]:
            parts = path.split("/")[:-1]
            folders.update("/".join(parts[: i + 1]) for i in range(len(parts)))
        return sorted(folders)

    def _note(self, path: str) -> Note:
        if path not in self.files:
            raise NoteNotFoundError(f"Note not found: {path}")
        snap = self._snapshot_note(path)
        return Note(
            path=path,
            content=self.files[path],
            frontmatter=snap.frontmatter,
            tags=snap.tags,
            links=snap.links,
            headings=snap.headings,
            modified=NOW,
            size=snap.size,
        )

    # -- whole vault ---------------------------------------------------------------------

    async def snapshot(self, folder: str = "") -> VaultSnapshot:
        self.calls.append("snapshot")
        prefix = _prefix(folder)
        paths = sorted(p for p in self.files if p.startswith(prefix) and p.endswith(".md"))
        return VaultSnapshot(
            notes=[self._snapshot_note(p) for p in paths],
            folders=[f for f in self._folders() if f.startswith(prefix)],
        )

    async def list_files(self, folder: str = "", extension: str | None = None) -> list[FileInfo]:
        self.calls.append("list_files")
        prefix = _prefix(folder)
        if prefix and prefix.rstrip("/") not in self._folders():
            raise NoteNotFoundError(f"Folder not found: {folder}")
        return [
            self._info(p)
            for p in sorted(self.files)
            if p.startswith(prefix) and (not extension or p.endswith(f".{extension}"))
        ]

    # -- notes ---------------------------------------------------------------------------

    async def read_note(self, path: str) -> Note:
        self.calls.append("read_note")
        return self._note(path)

    async def write_note(self, path: str, content: str, overwrite: bool = False) -> str:
        self.calls.append("write_note")
        if path in self.files and not overwrite:
            raise NoteExistsError(f"Note already exists: {path}")
        self.files[path] = content
        self.writes.append(path)
        return path

    def _append(
        self,
        path: str,
        content: str,
        heading: str | None,
        create_heading: bool = False,
        as_line: bool = False,
    ) -> None:
        text = self.files[path]
        content += "\n" if as_line else ""
        nl = "" if not text or text.endswith("\n") else "\n"
        if heading is None:
            self.files[path] = f"{text}{nl}{content}"
            return
        wanted = heading.strip()
        level = len(wanted) - len(wanted.lstrip("#"))
        title = wanted.lstrip("#").strip().lower()
        lines = text.splitlines(keepends=True)
        marks = [(i, _HEADING.match(line)) for i, line in enumerate(lines)]
        found = [(i, m) for i, m in marks if m]
        for n, (i, m) in enumerate(found):
            assert m
            if m.group(2).lower() == title and level in (0, len(m.group(1))):
                end = next(
                    (j for j, m2 in found[n + 1 :] if m2 and len(m2.group(1)) <= len(m.group(1))),
                    len(lines),
                )
                section = "".join(lines[i + 1 : end])
                body = section.rstrip()
                self.files[path] = (
                    "".join(lines[: i + 1])
                    + body
                    + "\n"
                    + content
                    + section[len(body) :]
                    + "".join(lines[end:])
                )
                return
        if not create_heading:
            raise HeadingNotFoundError(f"Heading not found: {heading}")
        hashes = "#" * (level or 2)
        gap = "\n" if text.strip() else ""
        self.files[path] = f"{text}{nl}{gap}{hashes} {wanted.lstrip('#').strip()}\n\n{content}"

    async def append(
        self,
        path: str,
        content: str,
        heading: str | None = None,
        *,
        create_heading: bool = False,
        as_line: bool = False,
    ) -> None:
        self.calls.append("append")
        self._note(path)
        self._append(path, content, heading, create_heading, as_line)
        self.writes.append(path)

    async def append_unless_linked(
        self, path: str, target: str, content: str, heading: str | None = None
    ) -> bool:
        self.calls.append("append_unless_linked")
        if any(link.target == target for link in self._note(path).links):
            return False
        self._append(path, content, heading, False, True)
        self.writes.append(path)
        return True

    async def replace_body(
        self,
        path: str,
        body: str,
        *,
        properties: Mapping[str, object] | None = None,
        defaults: Mapping[str, object] | None = None,
    ) -> None:
        """The text after the frontmatter block replaced; only the given properties are edited."""
        self.calls.append("replace_body")
        note = self._note(path)
        block, _ = split_frontmatter(note.content)
        lines = block.splitlines(keepends=True)[1:-1]
        if (
            block
            and not note.frontmatter
            and any(line.strip() and not line.lstrip().startswith("#") for line in lines)
        ):
            raise InvalidArgumentError(
                f"{path} has frontmatter Obsidian cannot parse; fix it in Obsidian first."
            )
        for source, replace in ((defaults, False), (properties, True)):
            for key, value in (source or {}).items():
                entry = frontmatter_yaml({key: value}).splitlines(keepends=True)
                at = next(
                    (i for i, line in enumerate(lines) if re.match(f"{key}[ \\t]*:", line)), None
                )
                if at is None:
                    if replace or key not in note.frontmatter:
                        lines += entry
                elif replace:
                    end = at + 1
                    while end < len(lines) and lines[end].startswith((" ", "\t", "-")):
                        end += 1
                    lines[at:end] = entry
        gap = (
            "\n" if block and note.content[len(block) :].startswith("\n") else "" if block else "\n"
        )
        self.files[path] = f"---\n{''.join(lines)}---\n{gap}{body}"
        self.writes.append(path)

    async def delete(self, path: str, permanent: bool = False) -> None:
        self.calls.append("delete")
        if path not in self.files:
            raise NoteNotFoundError(f"Note not found: {path}")
        del self.files[path]
        (self.deleted if permanent else self.trashed).append(path)

    # -- tags ----------------------------------------------------------------------------

    async def update_tags(self, path: str, add: list[str], remove: list[str]) -> TagChange:
        """Case-insensitive like Obsidian; the file is not touched when nothing changes."""
        self.calls.append("update_tags")
        note = self._note(path)
        current = self._fm_tags(note.frontmatter)
        drop = {t.removeprefix("#").lower() for t in remove}
        removed = [t for t in current if t.lower() in drop]
        have = {t.lower() for t in current}
        added = _dedupe(
            [t.removeprefix("#") for t in add if t.removeprefix("#").lower() not in have]
        )
        tags = [t for t in current if t.lower() not in drop] + added
        if added or removed:
            block, body = split_frontmatter(note.content)
            kept: list[str] = []
            skipping = False
            for line in block.splitlines(keepends=True)[1:-1]:
                if _TAGS_ENTRY.match(line):
                    skipping = True
                elif not (skipping and line.startswith((" ", "-"))):
                    skipping = False
                    kept.append(line)
            entry = ["tags:\n", *(f"  - {t}\n" for t in tags)] if tags else []
            self.files[path] = "---\n" + "".join(kept) + "".join(entry) + "---\n" + body
            self.writes.append(path)
        return TagChange(tags=tags, added=added, removed=removed)

    async def tags(self) -> dict[str, int]:
        """Occurrences per tag, like Obsidian's tag pane (a tag used twice counts twice)."""
        self.calls.append("tags")
        counts: dict[str, int] = {}
        for path, text in self.files.items():
            if path.endswith(".md"):
                for tag in self._tag_uses(text):
                    counts[tag] = counts.get(tag, 0) + 1
        return counts

    async def notes_with_tag(self, tag: str, include_nested: bool = True) -> list[str]:
        self.calls.append("notes_with_tag")
        wanted = tag.removeprefix("#").lower()

        def matches(have: str) -> bool:
            have = have.lower()
            return have == wanted or (include_nested and have.startswith(f"{wanted}/"))

        return sorted(
            p
            for p in self.files
            if p.endswith(".md") and any(matches(t) for t in self._snapshot_note(p).tags)
        )

    # -- links ---------------------------------------------------------------------------

    async def outgoing_links(self, path: str) -> list[Link]:
        self.calls.append("outgoing_links")
        return self._note(path).links

    async def backlinks(self, path: str) -> list[str]:
        self.calls.append("backlinks")
        self._note(path)
        return sorted(
            p
            for p in self.files
            if p.endswith(".md") and any(k.target == path for k in self._links(self.files[p]))
        )

    async def resolve_link(self, link: str, source_path: str) -> str:
        self.calls.append("resolve_link")
        name = link.removesuffix(".md")
        for path in sorted(self.files):
            if path.endswith(".md") and name in (
                path.removesuffix(".md"),
                PurePosixPath(path).stem,
            ):
                return path
        raise NoteNotFoundError(f"No note matches the link: {link}")

    async def link_text(self, target_path: str, source_path: str) -> str:
        self.calls.append("link_text")
        return PurePosixPath(target_path).stem

    # -- search --------------------------------------------------------------------------

    async def search(self, query: str, folder: str | None = None, limit: int = 20) -> SearchResults:
        """Case-insensitive substring match per line (not Obsidian's query language)."""
        self.calls.append("search")
        prefix = _prefix(folder or "")
        needle = query.lower()
        hits = []
        for path in sorted(self.files):
            if not path.startswith(prefix) or not path.endswith(".md"):
                continue
            matches = [
                SearchMatch(line=n, text=line[:300])
                for n, line in enumerate(self.files[path].splitlines(), 1)
                if needle in line.lower()
            ]
            if matches:
                hits.append(SearchHit(path=path, matches=matches))
        return SearchResults(hits=hits[:limit], truncated=len(hits) > limit)

    # -- daily notes ---------------------------------------------------------------------

    async def daily_path(self, day: date) -> str:
        self.calls.append("daily_path")
        return f"{self.daily_folder}/{day.isoformat()}.md"

    async def read_daily(self, day: date) -> Note | None:
        self.calls.append("read_daily")
        path = await self.daily_path(day)
        return self._note(path) if path in self.files else None

    async def append_daily(self, content: str, day: date, heading: str | None = None) -> str:
        """Creates the note for any date, and a missing heading section, like the real vault."""
        self.calls.append("append_daily")
        path = await self.daily_path(day)
        self.files.setdefault(path, "")
        self._append(path, content, heading, create_heading=True)
        self.writes.append(path)
        return path
