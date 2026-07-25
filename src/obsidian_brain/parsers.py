"""Parsers for the text emitted by the Obsidian CLI."""

import re
from typing import Any

import frontmatter


def _parse_markdown(text: str) -> dict[str, Any]:
    """Split raw Markdown into content, normalized tags, and frontmatter."""
    stripped = text.lstrip("\n")
    post = frontmatter.loads(stripped)
    metadata = post.metadata
    if post.handler is None:
        content = text
    else:
        _, content = post.handler.split(stripped)
        content = content.lstrip("\n")

    tags = metadata.pop("tags", [])
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",")]
    elif not isinstance(tags, list):
        tags = []

    return {
        "content": content,
        "tags": tags,
        "frontmatter": metadata,
    }


def parse_note_read(data: str, path: str = "") -> dict[str, Any]:
    """Parse raw Markdown from ``obsidian read``."""
    return {
        "path": path,
        "raw": data,
        **_parse_markdown(data),
        "modified": None,
    }


def parse_search_results(data: str) -> list[dict[str, Any]]:
    """Group grep-style ``path:line: text`` search output by file."""
    matches_by_path: dict[str, list[str]] = {}
    for line in data.splitlines():
        match = re.match(r"^(.+?):\d+: ?(.*)$", line)
        if match:
            matches_by_path.setdefault(match.group(1), []).append(match.group(2))

    return [
        {"path": path, "matches": matches, "score": 0.0}
        for path, matches in matches_by_path.items()
    ]


def parse_daily(data: str) -> dict[str, Any]:
    """Parse raw Markdown from ``obsidian daily:read``."""
    return _parse_markdown(data)
