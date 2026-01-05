"""Utility modules for Obsidian Brain MCP."""

from .frontmatter import (
    add_frontmatter_tags,
    create_note_with_frontmatter,
    parse_note,
    remove_frontmatter_tags,
)
from .wikilinks import extract_wikilinks, inject_wikilink, resolve_wikilink

__all__ = [
    "extract_wikilinks",
    "inject_wikilink",
    "resolve_wikilink",
    "parse_note",
    "add_frontmatter_tags",
    "remove_frontmatter_tags",
    "create_note_with_frontmatter",
]
