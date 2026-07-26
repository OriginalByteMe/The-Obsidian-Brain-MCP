"""Parsers for the text emitted by the Obsidian CLI."""

import re
from typing import Any

import frontmatter
from yaml import YAMLError


def _parse_markdown(text: str) -> dict[str, Any]:
    """Split raw Markdown into content, normalized tags, and frontmatter."""
    stripped = text.lstrip("\n")
    try:
        post = frontmatter.loads(stripped)
    except YAMLError:
        return {"content": text, "tags": [], "frontmatter": {}}

    metadata = post.metadata
    if post.handler is None:
        content = text
    else:
        try:
            _, content = post.handler.split(stripped)
        except ValueError:
            # The opening delimiter is never closed: treat it all as content.
            return {"content": text, "tags": [], "frontmatter": {}}
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
        # Any extension: search covers notes, canvases and bases.
        match = re.match(r"^(.+?\.[A-Za-z0-9]+):\d+: ?(.*)$", line)
        if match:
            matches_by_path.setdefault(match.group(1), []).append(match.group(2))

    return [
        {"path": path, "matches": matches, "score": 0.0}
        for path, matches in matches_by_path.items()
    ]


def parse_daily(data: str) -> dict[str, Any]:
    """Parse raw Markdown from ``obsidian daily:read``."""
    return _parse_markdown(data)
