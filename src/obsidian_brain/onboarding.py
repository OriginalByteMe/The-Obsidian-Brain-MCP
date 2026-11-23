"""Vault onboarding: analyse a `VaultSnapshot` and render the config and starter memories.

Everything here is pure. The tools gather the snapshot and write the files. Files under
`Obsidian Brain/` (what onboarding itself generates) are never part of the analysis, so a
re-run sees the same vault the first run did.
"""

import math
import re
import unicodedata
from collections import Counter
from pathlib import PurePosixPath
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .memory import BRAIN_DIR, MEMORIES_PATH, memory_text
from .models import NoteSnapshot, VaultSnapshot

CONFIG_PATH = f"{BRAIN_DIR}/config.md"
OVERVIEW_PATH = f"{MEMORIES_PATH}/vault-overview.md"
CONVENTIONS_PATH = f"{MEMORIES_PATH}/conventions.md"

_YAML_FENCE = re.compile(r"```ya?ml[ \t]*\r?\n(.*?)\r?\n?```", re.DOTALL)

_PARA = {
    "projects": "Active projects with deadlines",
    "areas": "Ongoing areas of responsibility",
    "resources": "Reference materials and topics of interest",
}
_ARCHIVE = {"archive", "archives"}
_SPECIAL = {
    "templates": "Note templates",
    "template": "Note templates",
    "daily": "Daily notes",
    "daily notes": "Daily notes",
    "dailies": "Daily notes",
    "journal": "Journal entries",
    "journals": "Journal entries",
    "attachments": "File attachments",
    "assets": "Images and media",
    "inbox": "Unsorted/new notes",
    "maps of content": "Maps of content (index notes)",
    "mocs": "Maps of content (index notes)",
}
_ZETTEL = {"permanent", "literature", "fleeting", "inbox"}
_ACE = {"atlas", "calendar", "efforts"}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_COMPACT_DATE = re.compile(r"^\d{8}")
_ZETTEL_ID = re.compile(r"^\d{12,14}")
_PREFIXED = re.compile(r"^(?:[A-Z]{2,5}|\d{1,3})\s?[-_.:]\s?\S")


class TagUse(BaseModel):
    tag: str = Field(description="Tag without '#'.")
    count: int = Field(description="Notes carrying the tag.")


class VaultAnalysis(BaseModel):
    """What onboarding learned about the vault (files under `Obsidian Brain/` excluded)."""

    folder_patterns: list[str] = Field(description="Organisational systems detected, e.g. PARA.")
    folder_purposes: dict[str, str] = Field(description="Folder path -> what it is for.")
    depth_levels: int = Field(description="Deepest folder nesting (0 = no folders).")
    tag_prefixes: list[str] = Field(description="Root names of hierarchical tags used 3+ times.")
    tag_hierarchies: list[str] = Field(description="Root names of every hierarchical tag.")
    top_tags: list[TagUse] = Field(description="Up to 20 most used tags with note counts.")
    template_folder: str | None
    template_count: int
    common_frontmatter_keys: list[str]
    frontmatter_patterns: dict[str, str]
    naming_patterns: list[str]
    date_format: str | None
    uses_prefixes: bool
    uses_ids: bool


def is_generated(path: str) -> bool:
    """True for anything inside the folder this server writes to."""
    return path == BRAIN_DIR or path.startswith(f"{BRAIN_DIR}/")


def user_notes(snapshot: VaultSnapshot) -> list[NoteSnapshot]:
    """The vault's own notes: everything except `Obsidian Brain/`."""
    return [n for n in snapshot.notes if not is_generated(n.path)]


def user_folders(snapshot: VaultSnapshot) -> list[str]:
    """The vault's own folders: everything except `Obsidian Brain/`."""
    return [f for f in snapshot.folders if not is_generated(f)]


def tag_counts(notes: list[NoteSnapshot]) -> dict[str, int]:
    """Notes per tag, merged case-insensitively (first spelling seen wins), most used first."""
    counts: dict[str, int] = {}
    spelling: dict[str, str] = {}
    for note in notes:
        for tag in {t.casefold(): t for t in note.tags}.values():
            key = spelling.setdefault(tag.casefold(), tag)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def extract_yaml_body(content: str) -> str:
    """The YAML inside the first ```yaml fence, wherever it sits; the whole text if unfenced."""
    match = _YAML_FENCE.search(content)
    return match.group(1) if match else content


def _label(folder_name: str) -> str:
    """A folder name without numbering or emoji prefix, casefolded: '1- Projects' -> 'projects'."""
    return unicodedata.normalize("NFC", re.sub(r"^[\W\d_]+", "", folder_name)).casefold().strip()


def _analyze_folders(folders: list[str], notes: list[NoteSnapshot]) -> dict[str, Any]:
    top = [f for f in folders if "/" not in f]
    top_labels = {_label(f) for f in top}
    patterns: list[str] = []
    purposes: dict[str, str] = {}

    if set(_PARA) <= top_labels and top_labels & _ARCHIVE:
        patterns.append("PARA Method")
        for folder in top:
            label = _label(folder)
            if label in _PARA:
                purposes[folder] = _PARA[label]
            elif label in _ARCHIVE:
                purposes[folder] = "Inactive items from other categories"
    if len(top_labels & _ZETTEL) >= 2:
        patterns.append("Zettelkasten")
    if any(re.match(r"^\d{2}-\d{2}\b", f) for f in top):
        patterns.append("Johnny.Decimal")
    if top_labels >= _ACE:
        patterns.append("ACE Method")

    for folder in folders:
        purpose = _SPECIAL.get(_label(PurePosixPath(folder).name))
        if purpose:
            purposes.setdefault(folder, purpose)

    templates = sorted(
        (f for f in folders if _label(PurePosixPath(f).name) in {"templates", "template"}),
        key=lambda f: (f.count("/"), f),
    )
    template_folder = templates[0] if templates else None
    return {
        "folder_patterns": patterns or ["Custom/Flat Structure"],
        "folder_purposes": dict(sorted(purposes.items())),
        "depth_levels": max((f.count("/") + 1 for f in folders), default=0),
        "template_folder": template_folder,
        "template_count": sum(
            1 for n in notes if template_folder and n.path.startswith(f"{template_folder}/")
        ),
    }


def _analyze_tags(notes: list[NoteSnapshot]) -> dict[str, Any]:
    counts = tag_counts(notes)
    hierarchical = {t: c for t, c in counts.items() if "/" in t}
    prefix_uses: Counter[str] = Counter()
    for tag, count in hierarchical.items():
        prefix_uses[tag.split("/")[0]] += count
    return {
        "top_tags": [TagUse(tag=t, count=c) for t, c in list(counts.items())[:20]],
        "tag_hierarchies": sorted(prefix_uses),
        "tag_prefixes": [
            p for p, c in sorted(prefix_uses.items(), key=lambda i: (-i[1], i[0])) if c >= 3
        ][:10],
    }


def _analyze_frontmatter(notes: list[NoteSnapshot]) -> dict[str, Any]:
    keys: Counter[str] = Counter(k for n in notes for k in n.frontmatter)
    threshold = max(1, math.ceil(len(notes) * 0.1))
    common = [k for k, c in sorted(keys.items(), key=lambda i: (-i[1], i[0])) if c >= threshold]
    patterns: dict[str, str] = {}
    if {"date", "created"} & set(common):
        patterns["date_tracking"] = "Notes include creation/modification dates"
    if {"status", "stage"} & set(common):
        patterns["status_tracking"] = "Notes use status/stage tracking"
    if "project" in common:
        patterns["project_linking"] = "Notes are linked to projects"
    if "author" in common:
        patterns["authorship"] = "Notes track authorship"
    if "aliases" in common:
        patterns["aliases"] = "Notes use aliases for alternate names"
    return {"common_frontmatter_keys": common[:20], "frontmatter_patterns": patterns}


def _analyze_naming(notes: list[NoteSnapshot]) -> dict[str, Any]:
    names = [PurePosixPath(n.path).stem for n in notes]
    total = len(names)
    patterns: list[str] = []
    date_format = None
    iso = sum(1 for f in names if _ISO_DATE.match(f))
    dated = sum(1 for f in names if _ISO_DATE.match(f) or _COMPACT_DATE.match(f))
    if dated > total * 0.1:
        patterns.append("Date-prefixed notes")
        date_format = "YYYY-MM-DD" if iso > dated / 2 else "YYYYMMDD"
    has_ids = sum(1 for f in names if _ZETTEL_ID.match(f)) > total * 0.1
    if has_ids:
        patterns.append("Zettelkasten IDs")

    # Date- and ID-named notes say nothing about how people name the rest.
    plain = [
        f
        for f in names
        if not (_ISO_DATE.match(f) or _COMPACT_DATE.match(f) or _ZETTEL_ID.match(f))
    ]
    uses_prefixes = sum(1 for f in plain if _PREFIXED.match(f)) > len(plain) * 0.1
    if uses_prefixes:
        patterns.append("Prefix-based naming")
    lettered = [f for f in plain if f[:1].isalpha()]
    capitalised = sum(1 for f in lettered if f[0].isupper())
    if lettered and capitalised > len(lettered) * 0.8:
        patterns.append("Title Case naming")
    elif lettered and capitalised < len(lettered) * 0.2:
        patterns.append("lowercase naming")
    return {
        "naming_patterns": patterns or ["Standard naming"],
        "date_format": date_format,
        "uses_prefixes": uses_prefixes,
        "uses_ids": has_ids,
    }


def analyze_vault(snapshot: VaultSnapshot) -> VaultAnalysis:
    """Detect organisation, tag, frontmatter and naming conventions from a snapshot."""
    notes = user_notes(snapshot)
    return VaultAnalysis(
        **_analyze_folders(user_folders(snapshot), notes),
        **_analyze_tags(notes),
        **_analyze_frontmatter(notes),
        **_analyze_naming(notes),
    )


def render_config(a: VaultAnalysis, now: str) -> str:
    """config.md: the profile as YAML inside a fence, so Obsidian renders it as code."""
    config = {
        "version": "1.0",
        "created": now,
        "vault_profile": {
            "organizational_systems": a.folder_patterns,
            "folder_purposes": a.folder_purposes,
            "depth_levels": a.depth_levels,
        },
        "conventions": {
            "tag_prefixes": a.tag_prefixes,
            "tag_hierarchies": a.tag_hierarchies,
            "naming_patterns": a.naming_patterns,
            "date_format": a.date_format,
            "uses_ids": a.uses_ids,
            "uses_prefixes": a.uses_prefixes,
        },
        "templates": {"folder": a.template_folder, "count": a.template_count},
        "frontmatter": {
            "common_keys": a.common_frontmatter_keys,
            "patterns": a.frontmatter_patterns,
        },
    }
    return f"```yaml\n{yaml.safe_dump(config, sort_keys=False, allow_unicode=True)}```\n"


def _memory_meta(kind: str, now: str) -> dict[str, object]:
    return {"name": kind, "type": kind, "created": now, "updated": now, "auto_generated": True}


def render_overview(a: VaultAnalysis, now: str) -> str:
    """The `vault-overview` memory: what the analysis found, as readable markdown."""
    lines = [
        "# Vault Overview",
        "",
        "This vault has been analyzed and the following patterns were discovered.",
        "",
        "## Organizational System",
        "",
        f"**Detected Pattern(s)**: {', '.join(a.folder_patterns)}",
        "",
    ]
    if a.folder_purposes:
        lines.append("**Key Folders**:")
        lines.extend(f"- `{folder}/`: {purpose}" for folder, purpose in a.folder_purposes.items())
        lines.append("")
    lines += [f"**Folder Depth**: {a.depth_levels} levels", "", "## Tag Conventions", ""]
    if a.tag_prefixes:
        lines += [f"**Tag Prefixes**: {', '.join(f'#{p}/' for p in a.tag_prefixes)}", ""]
    if a.top_tags:
        lines.append("**Top 10 Tags**:")
        lines.extend(f"- #{t.tag} ({t.count} notes)" for t in a.top_tags[:10])
        lines.append("")
    lines += ["## Naming Conventions", ""]
    lines.extend(f"- {p}" for p in a.naming_patterns)
    if a.date_format:
        lines.append(f"- Date format: `{a.date_format}`")
    lines.append("")
    if a.common_frontmatter_keys:
        keys = ", ".join(f"`{k}`" for k in a.common_frontmatter_keys[:10])
        lines += ["## Frontmatter Conventions", "", f"**Common Keys**: {keys}", ""]
        lines.extend(f"- **{p}**: {d}" for p, d in a.frontmatter_patterns.items())
        if a.frontmatter_patterns:
            lines.append("")
    if a.template_folder:
        lines += [
            "## Templates",
            "",
            f"**Template Folder**: `{a.template_folder}`",
            f"**Templates Found**: {a.template_count}",
            "",
        ]
    lines += ["---", "", "*Auto-generated during onboarding. Update as your vault evolves.*"]
    return memory_text(_memory_meta("vault-overview", now), "\n".join(lines))


def render_conventions(a: VaultAnalysis, now: str) -> str:
    """The `conventions` memory: how to keep new notes consistent with the vault."""
    lines = ["# Vault Conventions", "", "Guidelines for maintaining consistency in this vault.", ""]
    lines += ["## Note Creation", ""]
    if a.date_format:
        lines.append(f"- Use `{a.date_format}` date format for date-prefixed notes")
    if a.uses_ids:
        lines.append("- Include Zettelkasten-style timestamp IDs for permanent notes")
    if "Title Case naming" in a.naming_patterns:
        lines.append("- Use Title Case for note names")
    lines += ["", "## Tagging", ""]
    if a.tag_prefixes:
        lines.append("Use hierarchical tags with these root prefixes:")
        lines.extend(f"- `#{p}/...`" for p in a.tag_prefixes)
        lines.append("")
    if a.common_frontmatter_keys:
        lines += ["## Frontmatter", "", "Include these standard frontmatter keys:", ""]
        lines.extend(f"- `{k}`" for k in a.common_frontmatter_keys[:8])
        lines.append("")
    if a.folder_purposes:
        lines += ["## File Organization", ""]
        lines.extend(f"- Place {p.lower()} in `{f}/`" for f, p in a.folder_purposes.items())
        lines.append("")
    lines += ["---", "", "*Update this memory as conventions evolve.*"]
    return memory_text(_memory_meta("conventions", now), "\n".join(lines))
