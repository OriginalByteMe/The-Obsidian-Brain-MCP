"""
CLI JSON output parsing functions for Obsidian Brain MCP.

Each function converts raw CLI JSON output into normalized Python data structures.
All parsers are defensive -- they use .get() with defaults and handle both
dict and JSON string inputs gracefully.

Since exact CLI JSON shapes may vary (see RESEARCH.md open questions),
parsers handle multiple possible formats for each command.
"""

import json
from typing import Any


def _ensure_dict(data: dict | str) -> dict:
    """Parse JSON string to dict if needed."""
    if isinstance(data, str):
        return json.loads(data)
    return data


def _ensure_list(data: list | str) -> list:
    """Parse JSON string to list if needed."""
    if isinstance(data, str):
        return json.loads(data)
    return data


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter from markdown text.

    Returns (frontmatter_dict, body) where body is the content after
    the closing ``---``.  If no frontmatter is found, returns ({}, text).
    """
    stripped = text.lstrip("\n")
    if not stripped.startswith("---"):
        return {}, text

    end = stripped.find("---", 3)
    if end == -1:
        return {}, text

    yaml_block = stripped[3:end].strip()
    body = stripped[end + 3:].lstrip("\n")

    # Simple YAML-like key: value parsing (avoids PyYAML dependency)
    frontmatter: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in yaml_block.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # List item under a key
        if line_stripped.startswith("- ") and current_key is not None:
            if current_list is None:
                current_list = []
            current_list.append(line_stripped[2:].strip().strip('"').strip("'"))
            frontmatter[current_key] = current_list
            continue

        # Key: value pair
        if ":" in line_stripped:
            # Flush previous list
            current_list = None
            colon_idx = line_stripped.index(":")
            key = line_stripped[:colon_idx].strip()
            value = line_stripped[colon_idx + 1:].strip()
            current_key = key
            if value:
                # Remove surrounding quotes
                value = value.strip('"').strip("'")
                frontmatter[key] = value
            # else: value will be set by list items or left empty

    return frontmatter, body


def parse_note_read(data: dict | str, path: str = "") -> dict[str, Any]:
    """Parse output from `obsidian read path="..."`.

    The CLI returns raw markdown text (not JSON).  This function
    extracts YAML frontmatter and tags from the content.

    Also handles the legacy dict format for backward compatibility
    with tests.

    Returns:
        Normalized dict with keys: path, content, tags, frontmatter, modified.
    """
    # Legacy dict format (from tests / future JSON support)
    if isinstance(data, dict):
        return {
            "path": data.get("path", path),
            "content": data.get("content", ""),
            "tags": data.get("tags", []),
            "frontmatter": data.get("frontmatter", {}),
            "modified": data.get("modified", None),
        }

    # Try JSON string (legacy compat)
    if isinstance(data, str) and data.lstrip().startswith("{"):
        try:
            d = json.loads(data)
            if isinstance(d, dict):
                return {
                    "path": d.get("path", path),
                    "content": d.get("content", ""),
                    "tags": d.get("tags", []),
                    "frontmatter": d.get("frontmatter", {}),
                    "modified": d.get("modified", None),
                }
        except (json.JSONDecodeError, ValueError):
            pass

    # Raw markdown string from CLI
    frontmatter, body = _parse_frontmatter(data)
    tags = frontmatter.pop("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    return {
        "path": path,
        "content": body,
        "tags": tags,
        "frontmatter": frontmatter,
        "modified": None,
    }


def parse_file_list(data: list | str) -> list[str]:
    """Parse CLI JSON output from `obsidian files ... format=json`.

    Expected input shapes:
        ["file1.md", "file2.md", ...]           # list of strings
        [{"path": "file1.md"}, ...]             # list of dicts

    Returns:
        List of file path strings.
    """
    items = _ensure_list(data)
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.append(item.get("path", item.get("name", "")))
        else:
            result.append(str(item))
    return result


def parse_search_results(data: list | str) -> list[dict[str, Any]]:
    """Parse CLI JSON output from `obsidian search query="..." format=json`.

    Expected input shape:
        [
            {
                "path": "Projects/MyProject.md",
                "matches": ["matched **text** snippet"],
                "score": 0.95
            },
            ...
        ]

    Returns:
        List of normalized result dicts with keys: path, matches, score.
    """
    items = _ensure_list(data)
    results = []
    for item in items:
        if isinstance(item, dict):
            results.append({
                "path": item.get("path", item.get("file", "")),
                "matches": item.get("matches", item.get("snippets", [])),
                "score": item.get("score", 0.0),
            })
        else:
            results.append({"path": str(item), "matches": [], "score": 0.0})
    return results


def parse_tags(data: dict | list | str) -> dict[str, int]:
    """Parse CLI JSON output from `obsidian tags format=json`.

    Expected input shapes:
        {"project": 5, "active": 3, ...}                  # dict format
        [{"tag": "project", "count": 5}, ...]              # list format

    Returns:
        Dict mapping tag names to occurrence counts.
    """
    if isinstance(data, str):
        data = json.loads(data)

    if isinstance(data, dict):
        return {k: int(v) for k, v in data.items()}
    elif isinstance(data, list):
        result: dict[str, int] = {}
        for item in data:
            if isinstance(item, dict):
                tag = item.get("tag", item.get("name", ""))
                count = item.get("count", item.get("total", 0))
                if tag:
                    result[tag] = int(count)
        return result
    return {}


def parse_daily(data: dict | str) -> dict[str, Any]:
    """Parse output from `obsidian daily:read`.

    The CLI returns raw markdown text (not JSON).  This function
    extracts YAML frontmatter and tags from the content.

    Also handles the legacy dict format for backward compatibility.

    Returns:
        Normalized dict with keys: content, tags, frontmatter.
    """
    # Legacy dict format
    if isinstance(data, dict):
        return {
            "content": data.get("content", ""),
            "tags": data.get("tags", []),
            "frontmatter": data.get("frontmatter", {}),
        }

    # Try JSON string (legacy compat)
    if isinstance(data, str) and data.lstrip().startswith("{"):
        try:
            d = json.loads(data)
            if isinstance(d, dict):
                return {
                    "content": d.get("content", ""),
                    "tags": d.get("tags", []),
                    "frontmatter": d.get("frontmatter", {}),
                }
        except (json.JSONDecodeError, ValueError):
            pass

    # Raw markdown string from CLI
    frontmatter, body = _parse_frontmatter(data)
    tags = frontmatter.pop("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    return {
        "content": body,
        "tags": tags,
        "frontmatter": frontmatter,
    }
