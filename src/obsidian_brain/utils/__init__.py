"""Utility modules for Obsidian Brain MCP."""

from .frontmatter import (
    add_frontmatter_tags,
    create_note_with_frontmatter,
    remove_frontmatter_tags,
)
from .wikilinks import extract_wikilinks, inject_wikilink

__all__ = [
    "extract_wikilinks",
    "inject_wikilink",
    "add_frontmatter_tags",
    "remove_frontmatter_tags",
    "create_note_with_frontmatter",
]
