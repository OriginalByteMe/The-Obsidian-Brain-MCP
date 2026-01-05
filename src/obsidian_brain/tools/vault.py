"""
Vault file operation tools for Obsidian Brain MCP.

Provides tools for listing, reading, creating, and updating notes.
"""

import json
from typing import TYPE_CHECKING

from ..cache import vault_cache
from ..client import NoteNotFoundError, ObsidianClient
from ..models import FileEntry, NoteContent
from ..utils.frontmatter import create_note_with_frontmatter
from ..utils.wikilinks import extract_wikilinks, inject_wikilink

if TYPE_CHECKING:
    from mcp_use.server import MCPServer


class InvalidBacklinkError(Exception):
    """Raised when a backlink target doesn't exist."""

    def __init__(self, target: str):
        self.target = target
        super().__init__(f"Backlink target does not exist: {target}")


def register_vault_tools(server: "MCPServer") -> None:
    """Register all vault-related tools with the MCP server."""

    @server.tool()
    async def list_vault_files(path: str = "/") -> str:
        """
        List all files and folders at the specified vault path.

        Args:
            path: Relative path in vault (default: root "/")

        Returns:
            JSON array of file/folder entries with names and types
        """
        async with ObsidianClient() as client:
            entries = await client.list_directory(path)

            result = [
                FileEntry(name=e["name"], type=e["type"]).model_dump()
                for e in entries
            ]

            return json.dumps(result, indent=2)

    @server.tool()
    async def get_note(path: str) -> str:
        """
        Get the content and metadata of a specific note.

        Args:
            path: Path to the note (e.g., "Projects/MyProject.md")

        Returns:
            JSON with content, tags, links, and frontmatter
        """
        async with ObsidianClient() as client:
            try:
                data = await client.get_note(path, include_metadata=True)

                # Extract wikilinks from content
                outgoing_links = extract_wikilinks(data.get("content", ""))

                result = NoteContent(
                    path=path,
                    content=data.get("content", ""),
                    tags=data.get("tags", []),
                    outgoing_links=outgoing_links,
                    frontmatter=data.get("frontmatter", {}),
                    modified=data.get("modified"),
                )

                return result.model_dump_json(indent=2)
            except NoteNotFoundError:
                return json.dumps({
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Note not found: {path}",
                })

    @server.tool()
    async def create_note(
        path: str,
        content: str,
        tags: list[str] | None = None,
        backlinks: list[str] | None = None,
    ) -> str:
        """
        Create a new note with frontmatter tags and wikilinks.

        The title is auto-generated from the filename. Backlinks are validated
        to ensure target notes exist before being added.

        Args:
            path: Path for new note (e.g., "Research/AI Safety.md")
            content: Main content body (without frontmatter or title)
            tags: List of tags to add to frontmatter (optional)
            backlinks: List of note names to link to - validated for existence (optional)

        Returns:
            Confirmation message with created note path

        Raises:
            InvalidBacklinkError: If any backlink target does not exist
        """
        tags = tags or []
        backlinks = backlinks or []

        async with ObsidianClient() as client:
            # Validate backlinks exist
            for link in backlinks:
                # Try common path variations
                link_path = link if link.endswith(".md") else f"{link}.md"
                exists = await client.note_exists(link_path)

                if not exists:
                    # Try without folder prefix
                    simple_path = link_path.split("/")[-1]
                    exists = await client.note_exists(simple_path)

                if not exists:
                    return json.dumps({
                        "error": True,
                        "type": "InvalidBacklinkError",
                        "message": f"Backlink target does not exist: {link}",
                    })

            # Extract title from path
            filename = path.split("/")[-1]
            if filename.endswith(".md"):
                filename = filename[:-3]
            title = filename

            # Create note with frontmatter
            note_content = create_note_with_frontmatter(
                title=title,
                content=content,
                tags=tags,
            )

            # Add backlinks under "See Also" section
            for link in backlinks:
                note_content = inject_wikilink(note_content, link)

            # Create the note
            await client.create_note(path, note_content)

            return json.dumps({
                "success": True,
                "path": path,
                "message": f"Created note: {path}",
                "tags": tags,
                "backlinks": backlinks,
            })

    @server.tool()
    async def update_note(path: str, content: str) -> str:
        """
        Replace the entire content of an existing note.

        Args:
            path: Path to the note
            content: New content (replaces everything including frontmatter)

        Returns:
            Confirmation message
        """
        async with ObsidianClient() as client:
            try:
                # Verify note exists first
                await client.get_note(path, include_metadata=False)
                await client.update_note(path, content)

                return json.dumps({
                    "success": True,
                    "path": path,
                    "message": f"Updated note: {path}",
                })
            except NoteNotFoundError:
                return json.dumps({
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Note not found: {path}",
                })

    @server.tool()
    async def append_to_note(
        path: str,
        content: str,
        heading: str | None = None,
    ) -> str:
        """
        Append content to an existing note.

        Args:
            path: Path to the note
            content: Content to append
            heading: Optional heading to append under (e.g., "## Notes")
                    If heading doesn't exist, it will be created

        Returns:
            Confirmation message
        """
        async with ObsidianClient() as client:
            try:
                if heading:
                    # Use PATCH with heading target
                    await client.patch_note(
                        path=path,
                        operation="append",
                        content=f"\n{content}",
                        target_type="heading",
                        target=heading,
                    )
                else:
                    # Simple append
                    await client.append_to_note(path, f"\n{content}")

                return json.dumps({
                    "success": True,
                    "path": path,
                    "message": f"Appended to note: {path}",
                    "heading": heading,
                })
            except NoteNotFoundError:
                return json.dumps({
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Note not found: {path}",
                })

    @server.tool()
    async def refresh_vault_structure() -> str:
        """
        Rebuild the cached vault structure.

        This scans the entire vault and rebuilds the structure cache including
        all folder hierarchies, note metadata, backlinks, and statistics.

        This is a potentially slow operation for large vaults.

        Returns:
            Summary of refreshed structure (note count, folder count, etc.)
        """
        async with ObsidianClient() as client:
            structure = await vault_cache.refresh(client)

            return json.dumps({
                "success": True,
                "message": "Vault structure refreshed",
                "stats": structure.stats.model_dump(),
                "refreshed_at": structure.refreshed_at.isoformat(),
            })

    @server.tool()
    async def delete_note(path: str) -> str:
        """
        Delete a note from the vault.

        Args:
            path: Path to the note to delete

        Returns:
            Confirmation message
        """
        async with ObsidianClient() as client:
            try:
                await client.delete_note(path)

                return json.dumps({
                    "success": True,
                    "path": path,
                    "message": f"Deleted note: {path}",
                })
            except NoteNotFoundError:
                return json.dumps({
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Note not found: {path}",
                })
