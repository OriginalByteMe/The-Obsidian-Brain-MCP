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


def parse_note_read(data: dict | str) -> dict[str, Any]:
    """Parse CLI JSON output from `obsidian read path="..." format=json`.

    Expected input shape:
        {
            "path": "Projects/MyProject.md",
            "content": "# My Project\\n...",
            "tags": ["project", "active"],
            "frontmatter": {"title": "My Project", ...},
            "modified": "2026-03-01T10:30:00Z"
        }

    Returns:
        Normalized dict with keys: path, content, tags, frontmatter, modified.
        Missing fields default to empty values.
    """
    d = _ensure_dict(data)
    return {
        "path": d.get("path", ""),
        "content": d.get("content", ""),
        "tags": d.get("tags", []),
        "frontmatter": d.get("frontmatter", {}),
        "modified": d.get("modified", None),
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
    """Parse CLI JSON output from `obsidian daily:read format=json`.

    Expected input shape:
        {
            "content": "# 2026-03-08\\n...",
            "tags": ["daily"],
            "frontmatter": {"date": "2026-03-08"}
        }

    Returns:
        Normalized dict with keys: content, tags, frontmatter.
    """
    d = _ensure_dict(data)
    return {
        "content": d.get("content", ""),
        "tags": d.get("tags", []),
        "frontmatter": d.get("frontmatter", {}),
    }
