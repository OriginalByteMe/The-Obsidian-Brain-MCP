"""
Dynamic vault access resources for Obsidian Brain MCP.

Provides resources for accessing individual notes and folder listings
via URI patterns like vault://note/{path} and vault://folder/{path}.
"""

import json
from typing import TYPE_CHECKING

from ..client import NoteNotFoundError, ObsidianAPIError, ObsidianClient

if TYPE_CHECKING:
    from mcp_use.server import MCPServer


def register_vault_access_resources(server: "MCPServer") -> None:
    """Register dynamic vault access resources with the MCP server."""

    @server.resource(
        uri="vault://note/{path:path}",
        mime_type="text/markdown",
    )
    async def get_vault_note(path: str) -> str:
        """
        Read a specific note from the vault by path.

        Returns the full content including frontmatter as markdown.

        Args:
            path: Note path relative to vault root (e.g., "Projects/MyNote.md")

        Returns:
            Full note content as markdown
        """
        async with ObsidianClient() as client:
            try:
                note_data = await client.get_note(path, include_metadata=False)
                return note_data.get("content", "")

            except NoteNotFoundError:
                return f"# Error: Note Not Found\n\nThe note `{path}` does not exist in the vault."
            except ObsidianAPIError as e:
                return f"# Error: API Error\n\n{e.message}"

    @server.resource(
        uri="vault://folder/{path:path}",
        mime_type="application/json",
    )
    async def get_vault_folder(path: str) -> str:
        """
        List all notes in a folder recursively.

        Returns JSON with folder metadata, notes list, and subfolders.
        Uses cache when available for performance.

        Args:
            path: Folder path relative to vault root (e.g., "Projects")

        Returns:
            JSON object with folder listing
        """
        from ..cache import CacheNotInitializedError, vault_cache

        # Normalize path for comparison
        folder_prefix = path.rstrip("/") + "/" if path else ""
        if folder_prefix == "/":
            folder_prefix = ""

        try:
            # Try to use cache first (faster)
            if vault_cache.is_initialized:
                structure = vault_cache.get_structure()

                # Filter notes by path prefix
                matching_notes = []
                subfolders = set()

                for note in structure.notes:
                    if note.path.startswith(folder_prefix):
                        matching_notes.append({
                            "path": note.path,
                            "title": note.title,
                            "tags": note.tags,
                        })

                        # Extract immediate subfolders
                        remaining_path = note.path[len(folder_prefix):]
                        if "/" in remaining_path:
                            subfolder = folder_prefix + remaining_path.split("/")[0]
                            subfolders.add(subfolder)

                result = {
                    "folder": path,
                    "notes": matching_notes,
                    "subfolders": sorted(list(subfolders)),
                    "total_notes": len(matching_notes),
                }
                return json.dumps(result, indent=2)

        except CacheNotInitializedError:
            pass  # Fall through to API approach

        # Fallback: Use API directly (slower but works without cache)
        async with ObsidianClient() as client:
            try:
                all_files = await client.get_all_files(path if path else "/")
                md_files = [f for f in all_files if f.endswith(".md")]

                notes = []
                for file_path in md_files:
                    try:
                        note_data = await client.get_note(file_path, include_metadata=True)
                        # Extract title from filename or use path
                        title = file_path.split("/")[-1]
                        if title.endswith(".md"):
                            title = title[:-3]

                        notes.append({
                            "path": file_path,
                            "title": title,
                            "tags": note_data.get("tags", []),
                        })
                    except Exception:
                        continue

                # Extract subfolders from file paths
                subfolders = set()
                for file_path in md_files:
                    remaining = file_path[len(folder_prefix):] if folder_prefix else file_path
                    if "/" in remaining:
                        subfolder = folder_prefix + remaining.split("/")[0]
                        subfolders.add(subfolder)

                result = {
                    "folder": path,
                    "notes": notes,
                    "subfolders": sorted(list(subfolders)),
                    "total_notes": len(notes),
                }
                return json.dumps(result, indent=2)

            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "message": f"Failed to list folder: {e.message}",
                })
