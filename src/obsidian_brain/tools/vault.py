"""
Vault file operation tools for Obsidian Brain MCP.

Provides tools for listing, reading, creating, and updating notes.
"""

import json
import re

from mcp.server.fastmcp import FastMCP

from ..cache import vault_cache
from ..exceptions import NoteNotFoundError
from ..models import FileEntry, NoteContent
from ..protocol import VaultClient
from ..utils.frontmatter import create_note_with_frontmatter
from ..utils.wikilinks import extract_wikilinks, inject_wikilink
from .errors import OPERATIONAL_ERRORS, error_json


_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)")


def _find_heading(content: str, heading: str) -> int | None:
    """Return the end offset of an exact ATX heading outside fenced code."""
    fence: tuple[str, int] | None = None
    offset = 0

    for line in content.splitlines(keepends=True):
        text = line.rstrip("\r\n")
        match = _FENCE_RE.match(text)
        if match:
            marker, remainder = match.groups()
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1] and not remainder.strip():
                fence = None
            offset += len(line)
            continue

        if fence is None and text == heading and _HEADING_RE.match(text):
            return offset + len(text)

        offset += len(line)

    return None


def register_vault_tools(server: FastMCP, client: VaultClient) -> None:
    """Register all vault-related tools with the MCP server."""

    @server.tool()
    async def list_vault_files(path: str = "/") -> str:
        """
        List all files and folders at the specified vault path.

        Args:
            path: Relative path in vault (default: root "/")

        Returns:
            JSON array of file/folder entries with names and types
            Failures return {"error": true, "type": "<exception>", "message": "<details>"}.
        """
        try:
            entries = await client.list_directory(path)
            result = [FileEntry(name=e["name"], type=e["type"]).model_dump() for e in entries]
            return json.dumps(result, indent=2)
        except OPERATIONAL_ERRORS as error:
            return error_json(error)

    @server.tool()
    async def get_note(path: str) -> str:
        """
        Get the content and metadata of a specific note.

        Args:
            path: Path to the note (e.g., "Projects/MyProject.md")

        Returns:
            JSON with content, tags, links, and frontmatter
            Failures return {"error": true, "type": "<exception>", "message": "<details>"}.
        """
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
            Failures return {"error": true, "type": "<exception>", "message": "<details>"}.

        """
        tags = tags or []
        backlinks = backlinks or []

        try:
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
                    return json.dumps(
                        {
                            "error": True,
                            "type": "InvalidBacklinkError",
                            "message": f"Backlink target does not exist: {link}",
                        }
                    )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)

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

        try:
            await client.create_note(path, note_content)
            if vault_cache.is_initialized:
                await vault_cache.sync_note(client, path)
        except OPERATIONAL_ERRORS as error:
            return error_json(error)

        return json.dumps(
            {
                "success": True,
                "path": path,
                "message": f"Created note: {path}",
                "tags": tags,
                "backlinks": backlinks,
            }
        )

    @server.tool()
    async def update_note(path: str, content: str) -> str:
        """
        Replace the entire content of an existing note.

        Args:
            path: Path to the note
            content: New content (replaces everything including frontmatter)

        Returns:
            Confirmation message
            Failures return {"error": true, "type": "<exception>", "message": "<details>"}.
        """
        try:
            # Verify note exists first
            await client.get_note(path, include_metadata=False)
            await client.update_note(path, content)
            if vault_cache.is_initialized:
                await vault_cache.sync_note(client, path)

            return json.dumps(
                {
                    "success": True,
                    "path": path,
                    "message": f"Updated note: {path}",
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
            Failures return {"error": true, "type": "<exception>", "message": "<details>"}.
        """
        try:
            if heading:
                # With heading: get current content, find/create heading, append under it
                data = await client.get_note(path, include_metadata=False)
                current = data.get("raw", data.get("content", ""))

                idx = _find_heading(current, heading)
                if idx is not None:
                    new_content = current[:idx] + f"\n{content}" + current[idx:]
                else:
                    new_content = current + f"\n\n{heading}\n\n{content}"

                await client.update_note(path, new_content)
            else:
                # Simple append
                await client.append_to_note(path, f"\n{content}")
            if vault_cache.is_initialized:
                await vault_cache.sync_note(client, path)

            return json.dumps(
                {
                    "success": True,
                    "path": path,
                    "message": f"Appended to note: {path}",
                    "heading": heading,
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
    async def refresh_vault_structure() -> str:
        """
        Rebuild the cached vault structure.

        This scans the entire vault and rebuilds the structure cache including
        all folder hierarchies, note metadata, backlinks, and statistics.

        This is a potentially slow operation for large vaults.

        Returns:
            Summary of refreshed structure (note count, folder count, etc.)
            Failures return {"error": true, "type": "<exception>", "message": "<details>"}.
        """
        try:
            structure = await vault_cache.refresh(client)
            return json.dumps(
                {
                    "success": True,
                    "message": "Vault structure refreshed",
                    "stats": structure.stats.model_dump(),
                    "refreshed_at": structure.refreshed_at.isoformat(),
                }
            )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)

    @server.tool()
    async def delete_note(path: str) -> str:
        """
        Delete a note from the vault.

        Args:
            path: Path to the note to delete

        Returns:
            Confirmation message
            Failures return {"error": true, "type": "<exception>", "message": "<details>"}.
        """
        try:
            await client.delete_note(path)
            if vault_cache.is_initialized:
                vault_cache.invalidate_path(path, exists=False)

            return json.dumps(
                {
                    "success": True,
                    "path": path,
                    "message": f"Deleted note: {path}",
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
