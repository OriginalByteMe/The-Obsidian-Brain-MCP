"""Memory naming and file format: pure helpers shared by memories, onboarding and the knowledge base.

A memory is a markdown file under `Obsidian Brain/memories/`. Its identity is a slug of its
name, so `list_memories`, `read_memory`, `write_memory` and `delete_memory` all agree on which
file a name means. Frontmatter values come from Obsidian (`Note.frontmatter`); the only text
parsing here is locating the frontmatter block, by lines, so a `---` inside a value is safe.
"""

import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime

import yaml

from .exceptions import InvalidArgumentError

BRAIN_DIR = "Obsidian Brain"
MEMORIES_PATH = f"{BRAIN_DIR}/memories"

# Longest slug (UTF-8 bytes) that still leaves room for ".md" inside a 255-byte file name.
_MAX_SLUG_BYTES = 200

# The frontmatter block: an opening `---` line, then the first line that is only `---`.
_FRONTMATTER = re.compile(r"\A\ufeff?---[ \t]*\r?\n(?:.*?\r?\n)?---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def utc_now() -> str:
    """Current UTC time as `2026-11-23T03:24:12Z`."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def display_name(name: str) -> str:
    """The name as stored: NFC, whitespace collapsed, without a trailing `.md`."""
    text = " ".join(unicodedata.normalize("NFC", name).split())
    return text[:-3].rstrip() if text.lower().endswith(".md") else text


def slugify(name: str) -> str:
    """The stable file stem for a memory name; raises when nothing usable is left.

    NFC-normalised and casefolded, every run of characters that are not letters, digits or
    combining marks becomes one `-`. 'Project X', 'project_x' and 'PROJECT-X' share the slug
    `project-x`; 'A/B' and 'AB' do not.
    """
    text = unicodedata.normalize("NFC", display_name(name).casefold())
    text = "".join(c if c.isalnum() or unicodedata.category(c)[0] == "M" else "-" for c in text)
    slug = re.sub(r"-+", "-", text).strip("-")
    if not slug:
        raise InvalidArgumentError(
            f"Memory name {name!r} has no letters or digits to build a file name from."
        )
    if len(slug.encode()) > _MAX_SLUG_BYTES:
        raise InvalidArgumentError(
            f"Memory name is too long ({len(slug.encode())} bytes after normalising; "
            f"the limit is {_MAX_SLUG_BYTES})."
        )
    return slug


def memory_name_of(path: str) -> str:
    """The name a memory file answers to when it has no `name` property: its path in the folder."""
    return path.removeprefix(f"{MEMORIES_PATH}/").removesuffix(".md")


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split file text into (frontmatter block with fences, body); the block is '' if absent.

    One blank line after the block belongs to the block, so `memory_text` and this are inverses.
    """
    match = _FRONTMATTER.match(text)
    if not match:
        return "", text
    return match.group(), re.sub(r"\A\r?\n", "", text[match.end() :], count=1)


def frontmatter_yaml(frontmatter: Mapping[str, object]) -> str:
    """The YAML lines of a mapping (keys in given order), each ending in a newline."""
    return yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, width=1_000_000, default_flow_style=False
    )


def frontmatter_block(frontmatter: Mapping[str, object]) -> str:
    """Render a dict as a `---` fenced YAML block (always valid YAML, keys in given order)."""
    return f"---\n{frontmatter_yaml(frontmatter)}---\n"


def memory_text(frontmatter: Mapping[str, object], body: str) -> str:
    """Full file text for a memory: frontmatter block, one blank line, body."""
    return f"{frontmatter_block(frontmatter)}\n{body}"
