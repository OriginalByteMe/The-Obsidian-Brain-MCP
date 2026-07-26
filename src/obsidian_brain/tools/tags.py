"""
Tag management tools for Obsidian Brain MCP.

Provides tools for adding, removing, and querying tags across the vault.
"""

import json

from mcp.server.fastmcp import FastMCP

from ..cache import CacheNotInitializedError, vault_cache
from ..exceptions import NoteNotFoundError
from ..protocol import VaultClient
from ..utils.frontmatter import add_frontmatter_tags, remove_frontmatter_tags
from .errors import OPERATIONAL_ERRORS, error_json


def register_tag_tools(server: FastMCP, client: VaultClient) -> None:
    """Register all tag-related tools with the MCP server."""

    @server.tool()
    async def add_tags(path: str, tags: list[str]) -> str:
        """
        Add tags to a note's frontmatter.

        Existing tags are preserved; duplicates are ignored.
        Tags are sorted alphabetically after addition.

        Args:
            path: Path to the note
            tags: List of tags to add (without # prefix)

        Returns:
            Confirmation with updated tag list
        """
        if not tags:
            return json.dumps(
                {
                    "error": True,
                    "type": "ValidationError",
                    "message": "No tags provided to add",
                }
            )

        # Normalize tags (remove # if present)
        normalized_tags = [t.lstrip("#") for t in tags]

        try:
            # Get current content
            data = await client.get_note(path)
            content = data.get("raw", data.get("content", ""))
            current_tags = data.get("tags", [])

            # Add new tags
            new_content = add_frontmatter_tags(content, normalized_tags)

            # Update the note
            await client.update_note(path, new_content)
            await vault_cache.sync_note(client, path)

            # Get updated tag list
            updated_tags = sorted(set(current_tags + normalized_tags))

            return json.dumps(
                {
                    "success": True,
                    "path": path,
                    "added_tags": normalized_tags,
                    "all_tags": updated_tags,
                    "message": f"Added {len(normalized_tags)} tag(s) to {path}",
                }
            )
        except NoteNotFoundError:
            return json.dumps(
                {
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Note not found: {path}",
                }
            )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)

    @server.tool()
    async def remove_tags(path: str, tags: list[str]) -> str:
        """
        Remove tags from a note's frontmatter.

        If all tags are removed, the tags field is removed from frontmatter.

        Args:
            path: Path to the note
            tags: List of tags to remove (without # prefix)

        Returns:
            Confirmation with updated tag list
        """
        if not tags:
            return json.dumps(
                {
                    "error": True,
                    "type": "ValidationError",
                    "message": "No tags provided to remove",
                }
            )

        # Normalize tags
        normalized_tags = [t.lstrip("#") for t in tags]

        try:
            # Get current content
            data = await client.get_note(path)
            content = data.get("raw", data.get("content", ""))
            current_tags = data.get("tags", [])

            # Remove tags
            new_content = remove_frontmatter_tags(content, normalized_tags)

            # Update the note
            await client.update_note(path, new_content)
            await vault_cache.sync_note(client, path)

            # Calculate remaining tags
            remaining_tags = [
                t for t in current_tags if t.lower() not in [x.lower() for x in normalized_tags]
            ]

            return json.dumps(
                {
                    "success": True,
                    "path": path,
                    "removed_tags": normalized_tags,
                    "remaining_tags": remaining_tags,
                    "message": f"Removed {len(normalized_tags)} tag(s) from {path}",
                }
            )
        except NoteNotFoundError:
            return json.dumps(
                {
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Note not found: {path}",
                }
            )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)

    @server.tool()
    async def list_all_tags() -> str:
        """
        Get all unique tags used across the vault with counts.

        Uses the cached vault structure for fast lookup.
        Call refresh_vault_structure first if cache is not initialized.

        Returns:
            JSON object mapping tag names to usage counts, sorted by count
        """
        try:
            tag_counts = vault_cache.get_all_tags()

            # Sort by count (descending), then by name
            sorted_tags = dict(sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])))

            return json.dumps(
                {
                    "success": True,
                    "tags": sorted_tags,
                    "total_unique_tags": len(sorted_tags),
                    "total_tag_usage": sum(sorted_tags.values()),
                }
            )
        except CacheNotInitializedError:
            return json.dumps(
                {
                    "error": True,
                    "type": "CacheNotInitializedError",
                    "message": "Vault cache not initialized. Call refresh_vault_structure first.",
                }
            )

    @server.tool()
    async def get_notes_by_tag(tag: str) -> str:
        """
        Get all notes that have a specific tag.

        Uses the cached vault structure for fast lookup.
        Call refresh_vault_structure first if cache is not initialized.

        Args:
            tag: Tag to search for (without # prefix)

        Returns:
            JSON array of note paths with this tag
        """
        # Normalize tag
        normalized_tag = tag.lstrip("#")

        try:
            note_paths = vault_cache.get_notes_by_tag(normalized_tag)

            return json.dumps(
                {
                    "success": True,
                    "tag": normalized_tag,
                    "notes": sorted(note_paths),
                    "count": len(note_paths),
                }
            )
        except CacheNotInitializedError:
            return json.dumps(
                {
                    "error": True,
                    "type": "CacheNotInitializedError",
                    "message": "Vault cache not initialized. Call refresh_vault_structure first.",
                }
            )
