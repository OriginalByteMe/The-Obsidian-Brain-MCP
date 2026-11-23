"""Knowledge base: vault statistics and a markdown overview, rendered from a `VaultSnapshot`.

Pure functions. Like onboarding, they leave out everything under `Obsidian Brain/`, so the
generated files never count as notes, orphans or links in the document describing the vault.
"""

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .memory import BRAIN_DIR, frontmatter_block
from .models import NoteSnapshot, VaultSnapshot
from .onboarding import tag_counts, user_folders, user_notes

KNOWLEDGE_BASE_PATH = f"{BRAIN_DIR}/knowledge-base.md"

GENERATOR = "obsidian-brain-mcp"

type _Tree = dict[str, _Tree]


class VaultStats(BaseModel):
    """Aggregate numbers for the vault, not counting `Obsidian Brain/`."""

    total_notes: int = Field(description="Markdown notes.")
    total_folders: int = Field(description="Folders at every depth.")
    total_tags: int = Field(description="Distinct tags (frontmatter and inline, case-insensitive).")
    total_links: int = Field(description="Distinct note-to-note links (self-links excluded).")
    orphan_notes: int = Field(description="Notes with no note-to-note links in or out.")


class KnowledgeBaseStatus(BaseModel):
    """Whether the knowledge base file exists and what it recorded when it was generated."""

    exists: bool
    path: str
    created: str | None = None
    updated: str | None = None
    stats: VaultStats | None = Field(default=None, description="Stats at generation time.")


def _link_graph(
    notes: list[NoteSnapshot],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(outgoing, incoming): distinct note-to-note links, links to non-notes ignored."""
    paths = {n.path for n in notes}

    outgoing = {
        n.path: {
            t for link in n.links if (t := link.target) is not None and t in paths and t != n.path
        }
        for n in notes
    }
    incoming: dict[str, set[str]] = defaultdict(set)
    for source, targets in outgoing.items():
        for target in targets:
            incoming[target].add(source)
    return outgoing, incoming


def _orphans(notes: list[NoteSnapshot]) -> list[str]:
    outgoing, incoming = _link_graph(notes)
    return sorted(n.path for n in notes if not outgoing[n.path] and not incoming[n.path])


def knowledge_base_status(frontmatter: dict[str, Any] | None) -> KnowledgeBaseStatus:
    """Status from the knowledge base file's frontmatter; None means the file does not exist."""
    if frontmatter is None:
        return KnowledgeBaseStatus(exists=False, path=KNOWLEDGE_BASE_PATH)
    try:
        stats = VaultStats.model_validate(frontmatter.get("vault_stats"))
    except ValidationError:
        stats = None
    created, updated = frontmatter.get("created"), frontmatter.get("updated")
    return KnowledgeBaseStatus(
        exists=True,
        path=KNOWLEDGE_BASE_PATH,
        created=None if created is None else str(created),
        updated=None if updated is None else str(updated),
        stats=stats,
    )


def compute_stats(snapshot: VaultSnapshot) -> VaultStats:
    """Statistics for the vault's own notes."""
    notes = user_notes(snapshot)
    outgoing, _ = _link_graph(notes)
    return VaultStats(
        total_notes=len(notes),
        total_folders=len(user_folders(snapshot)),
        total_tags=len(tag_counts(notes)),
        total_links=sum(len(targets) for targets in outgoing.values()),
        orphan_notes=len(_orphans(notes)),
    )


def _cell(text: object) -> str:
    """Make text safe inside a markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def _folder_tree(folders: list[str]) -> str:
    root: _Tree = {}
    for folder in folders:
        node = root
        for part in folder.split("/"):
            node = node.setdefault(part, {})

    def render(node: _Tree, prefix: str) -> list[str]:
        lines: list[str] = []
        for i, name in enumerate(sorted(node)):
            last = i == len(node) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{name}/")
            lines.extend(render(node[name], prefix + ("    " if last else "│   ")))
        return lines

    return "\n".join(["## Folder Structure", "", "```", "/", *render(root, ""), "```"])


def _tag_taxonomy(notes: list[NoteSnapshot]) -> str:
    counts = tag_counts(notes)
    lines = ["## Tag Taxonomy", ""]
    if not counts:
        return "\n".join([*lines, "*No tags found in vault.*"])
    example: dict[str, str] = {}
    for note in notes:
        for tag in note.tags:
            example.setdefault(tag.casefold(), note.path)
    lines += [
        "### Top Tags by Usage",
        "",
        "| Rank | Tag | Notes | Example Note |",
        "|------|-----|-------|--------------|",
    ]
    for rank, (tag, count) in enumerate(list(counts.items())[:20], 1):
        lines.append(
            f"| {rank} | {_cell('#' + tag)} | {count} | {_cell(example[tag.casefold()])} |"
        )
    roots: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for tag, count in counts.items():
        if "/" in tag:
            roots[tag.split("/")[0]].append((tag, count))
    if roots:
        lines += ["", "### Hierarchical Tags", ""]
        for root in sorted(roots):
            lines.append(f"- **#{root}**")
            lines.extend(f"  - #{tag} ({count})" for tag, count in roots[root])
    return "\n".join(lines)


def _hub_notes(notes: list[NoteSnapshot]) -> str:
    outgoing, incoming = _link_graph(notes)
    scored = sorted(
        ((n.path, len(incoming[n.path]), len(outgoing[n.path])) for n in notes),
        key=lambda row: (-(row[1] + row[2]), row[0]),
    )
    scored = [row for row in scored if row[1] + row[2] > 0][:15]
    lines = ["## Hub Notes (Most Connected)", ""]
    if not scored:
        return "\n".join([*lines, "*No connected notes found.*"])
    lines += [
        "Notes with the most distinct links in and out:",
        "",
        "| Note | Incoming | Outgoing | Total |",
        "|------|----------|----------|-------|",
    ]
    lines.extend(f"| {_cell(p)} | {i} | {o} | {i + o} |" for p, i, o in scored)
    return "\n".join(lines)


def _link_patterns(notes: list[NoteSnapshot]) -> str:
    outgoing, incoming = _link_graph(notes)

    def top(graph: dict[str, set[str]], title: str, blurb: str, unit: str) -> list[str]:
        rows = sorted(((p, len(s)) for p, s in graph.items() if s), key=lambda r: (-r[1], r[0]))
        if not rows:
            return []
        lines = [title, blurb, ""]
        lines.extend(f"{i}. **{_cell(p)}** ({n} {unit})" for i, (p, n) in enumerate(rows[:10], 1))
        return [*lines, ""]

    body = top(
        incoming,
        "### Most Referenced Notes",
        "Notes that are linked TO most often:",
        "backlinks",
    ) + top(
        outgoing, "### Most Linking Notes", "Notes that link OUT to the most notes:", "outgoing"
    )
    return "\n".join(["## Link Patterns", "", *(body or ["*No link patterns found.*"])]).rstrip()


def _orphan_notes(notes: list[NoteSnapshot]) -> str:
    orphans = _orphans(notes)
    lines = ["## Orphan Notes", ""]
    if not orphans:
        return "\n".join([*lines, "*No orphan notes found. All notes are connected!*"])
    lines += [f"Notes with no links to or from other notes ({len(orphans)} total):", ""]
    lines.extend(f"- `{path}`" for path in orphans[:20])
    if len(orphans) > 20:
        lines.append(f"- *...and {len(orphans) - 20} more*")
    return "\n".join(lines)


def render_knowledge_base(
    snapshot: VaultSnapshot,
    *,
    created: str,
    now: str,
    include_orphans: bool = True,
    include_link_patterns: bool = True,
) -> str:
    """The whole knowledge base file. `created` is carried over from the previous version."""
    notes = user_notes(snapshot)
    stats = compute_stats(snapshot)
    meta = {
        "created": created,
        "updated": now,
        "generator": GENERATOR,
        "vault_stats": stats.model_dump(),
    }
    overview = "\n".join(
        [
            "## Overview",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Notes | {stats.total_notes} |",
            f"| Folders | {stats.total_folders} |",
            f"| Tags | {stats.total_tags} |",
            f"| Links | {stats.total_links} |",
            f"| Orphans | {stats.orphan_notes} |",
        ]
    )
    sections = [
        frontmatter_block(meta).rstrip("\n"),
        "# Vault Knowledge Base\n\n"
        "> This file is auto-generated by Obsidian Brain MCP to help LLMs navigate this vault.\n"
        "> It leaves out the `Obsidian Brain/` folder itself. Regenerate it with the\n"
        "> `build_knowledge_base` tool when the vault changes significantly.",
        overview,
        _folder_tree(user_folders(snapshot)),
        _tag_taxonomy(notes),
        _hub_notes(notes),
    ]
    if include_link_patterns:
        sections.append(_link_patterns(notes))
    if include_orphans:
        sections.append(_orphan_notes(notes))
    sections.append(f"---\n\n*Generated by Obsidian Brain MCP on {now}*")
    return "\n\n".join(sections) + "\n"
