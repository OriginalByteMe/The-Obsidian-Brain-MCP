"""Cached vault file index and live Markdown note resources."""

from __future__ import annotations

import json
from pathlib import PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote

from ..cache import CacheNotInitializedError, vault_cache

if TYPE_CHECKING:
    from ..protocol import VaultClient

_REFRESH_HINT = "Call refresh_vault_structure to initialize or update this cached index."


def _decode_note_path(value: str) -> str:
    """Decode one URI-template value and reject paths outside the vault."""
    path = unquote(value, errors="strict")
    parts = path.split("/")
    if (
        not path.lower().endswith(".md")
        or "\0" in path
        or "\\" in path
        or PurePosixPath(path).is_absolute()
        or PureWindowsPath(path).drive
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("Invalid vault note path")
    return path


def register_note_resources(server, client: VaultClient) -> None:
    """Register the cached file index and parameterized Markdown note reader."""

    @server.resource("vault://files", mime_type="application/json")
    def vault_files() -> str:
        """List every cached vault file and whether it has a readable note URI.

        Each entry has ``path``, a lowercase ``extension``, and ``readable``.
        Markdown entries additionally expose a percent-encoded
        ``vault://note/{path}`` URI. Call refresh_vault_structure before first
        use and after out-of-band vault changes.
        """
        try:
            structure = vault_cache.get_structure()
            file_paths = vault_cache.get_file_paths()
        except CacheNotInitializedError:
            return json.dumps({"error": _REFRESH_HINT})

        files: list[dict[str, str | bool]] = []
        for path in sorted(file_paths):
            extension = PurePosixPath(path).suffix.lower()
            readable = extension == ".md"
            entry: dict[str, str | bool] = {
                "path": path,
                "extension": extension,
                "readable": readable,
            }
            if readable:
                entry["uri"] = f"vault://note/{quote(path, safe='')}"
            files.append(entry)

        return json.dumps(
            {
                "files": files,
                "refreshed_at": structure.refreshed_at.isoformat(),
                "refresh": _REFRESH_HINT,
            },
            ensure_ascii=False,
            indent=2,
        )

    @server.resource("vault://note/{path}", mime_type="text/markdown")
    async def vault_note(path: str) -> str:
        """Read current Markdown content for a validated vault-relative path."""
        note_path = _decode_note_path(path)
        note = await client.get_note(note_path, include_metadata=False)
        return note.get("content", "")
