"""
Daily note tools for Obsidian Brain MCP.

Provides tools for working with daily notes.
"""

import json
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from ..cache import vault_cache
from ..exceptions import NoteNotFoundError
from ..protocol import VaultClient
from ..utils.wikilinks import create_wikilink
from .errors import OPERATIONAL_ERRORS, error_json


def register_daily_tools(server: FastMCP, client: VaultClient) -> None:
    """Register all daily note tools with the MCP server."""

    async def _sync_daily_note(date: str) -> None:
        """Refresh the written daily note in the cached index, if resolvable."""
        try:
            path = await client.get_daily_path(date)
        except (NoteNotFoundError, *OPERATIONAL_ERRORS):
            return
        if path:
            await vault_cache.sync_note(client, path)

    @server.tool()
    async def get_daily_note(date: str | None = None) -> str:
        """
        Get the daily note for today or a specific date.

        Uses Obsidian's daily notes feature which requires the
        Daily Notes plugin to be configured.

        Args:
            date: Optional date in YYYY-MM-DD format (default: today)

        Returns:
            JSON with daily note content and metadata
        """
        # Use today if no date specified
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return json.dumps(
                {
                    "error": True,
                    "type": "ValidationError",
                    "message": f"Invalid date format: {date}. Use YYYY-MM-DD",
                }
            )

        try:
            data = await client.get_daily_note(date)

            return json.dumps(
                {
                    "success": True,
                    "date": date,
                    "content": data.get("content", ""),
                    "tags": data.get("tags", []),
                    "frontmatter": data.get("frontmatter", {}),
                }
            )
        except NoteNotFoundError:
            return json.dumps(
                {
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Daily note not found for {date}",
                }
            )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)

    @server.tool()
    async def append_to_daily(
        content: str,
        heading: str | None = None,
        date: str | None = None,
    ) -> str:
        """
        Append content to today's daily note.

        If the daily note doesn't exist, it may be created (depending on
        Obsidian plugin settings).

        Args:
            content: Content to append
            heading: Optional heading to prepend before content
            date: Optional date in YYYY-MM-DD format (default: today)

        Returns:
            Confirmation message
        """
        if not content or not content.strip():
            return json.dumps(
                {
                    "error": True,
                    "type": "ValidationError",
                    "message": "Content cannot be empty",
                }
            )

        # Use today if no date specified
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return json.dumps(
                {
                    "error": True,
                    "type": "ValidationError",
                    "message": f"Invalid date format: {date}. Use YYYY-MM-DD",
                }
            )

        try:
            if heading:
                # Format with heading
                if not heading.startswith("#"):
                    heading = f"## {heading}"
                append_content = f"\n\n{heading}\n\n{content}"
            else:
                append_content = f"\n{content}"

            await client.append_daily(append_content, date)
            await _sync_daily_note(date)

            return json.dumps(
                {
                    "success": True,
                    "date": date,
                    "heading": heading,
                    "message": f"Appended to daily note for {date}",
                }
            )
        except NoteNotFoundError:
            return json.dumps(
                {
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Daily note not found for {date}. It may need to be created first.",
                }
            )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)

    @server.tool()
    async def create_daily_entry(
        content: str,
        tags: list[str] | None = None,
        links: list[str] | None = None,
        date: str | None = None,
    ) -> str:
        """
        Create a structured entry in today's daily note.

        Entry format: "- [HH:MM] content [[links]] #tags"

        This creates a timestamped bullet point with optional inline tags
        and wikilinks. Useful for logging activities, meeting notes, or
        quick captures throughout the day.

        Args:
            content: Entry text
            tags: Optional inline tags to add (without # prefix)
            links: Optional note names to link (as wikilinks)
            date: Optional date in YYYY-MM-DD format (default: today)

        Returns:
            Confirmation message with the created entry
        """
        if not content or not content.strip():
            return json.dumps(
                {
                    "error": True,
                    "type": "ValidationError",
                    "message": "Entry content cannot be empty",
                }
            )

        # Use today if no date specified
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return json.dumps(
                {
                    "error": True,
                    "type": "ValidationError",
                    "message": f"Invalid date format: {date}. Use YYYY-MM-DD",
                }
            )

        tags = tags or []
        links = links or []

        # Build the entry
        timestamp = datetime.now().strftime("%H:%M")
        entry_parts = [f"- [{timestamp}] {content.strip()}"]

        # Add wikilinks
        for link in links:
            entry_parts.append(f" {create_wikilink(link)}")

        # Add inline tags
        for tag in tags:
            # Normalize tag (remove # if present)
            clean_tag = tag.lstrip("#")
            entry_parts.append(f" #{clean_tag}")

        entry = "".join(entry_parts)

        try:
            await client.append_daily(f"\n{entry}", date)
            await _sync_daily_note(date)

            return json.dumps(
                {
                    "success": True,
                    "date": date,
                    "entry": entry,
                    "timestamp": timestamp,
                    "tags": tags,
                    "links": links,
                    "message": f"Created entry in daily note for {date}",
                }
            )
        except NoteNotFoundError:
            return json.dumps(
                {
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Daily note not found for {date}. It may need to be created first.",
                }
            )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)
