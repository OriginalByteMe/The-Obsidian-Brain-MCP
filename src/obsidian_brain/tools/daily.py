"""
Daily/periodic note tools for Obsidian Brain MCP.

Provides tools for working with daily notes and other periodic notes
(weekly, monthly, etc.).
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING

from ..client import NoteNotFoundError, ObsidianAPIError, ObsidianClient
from ..utils.wikilinks import create_wikilink

if TYPE_CHECKING:
    from mcp_use.server import MCPServer


def register_daily_tools(server: "MCPServer") -> None:
    """Register all daily/periodic note tools with the MCP server."""

    @server.tool()
    async def get_daily_note(date: str | None = None) -> str:
        """
        Get the daily note for today or a specific date.

        Uses Obsidian's periodic notes feature which requires the
        Periodic Notes or Daily Notes plugin to be configured.

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
            return json.dumps({
                "error": True,
                "type": "ValidationError",
                "message": f"Invalid date format: {date}. Use YYYY-MM-DD",
            })

        async with ObsidianClient() as client:
            try:
                data = await client.get_periodic("daily", date)

                return json.dumps({
                    "success": True,
                    "date": date,
                    "content": data.get("content", ""),
                    "tags": data.get("tags", []),
                    "frontmatter": data.get("frontmatter", {}),
                })
            except NoteNotFoundError:
                return json.dumps({
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Daily note not found for {date}",
                })
            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

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
            heading: Optional heading to append under (e.g., "## Notes")
            date: Optional date in YYYY-MM-DD format (default: today)

        Returns:
            Confirmation message
        """
        if not content or not content.strip():
            return json.dumps({
                "error": True,
                "type": "ValidationError",
                "message": "Content cannot be empty",
            })

        # Use today if no date specified
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return json.dumps({
                "error": True,
                "type": "ValidationError",
                "message": f"Invalid date format: {date}. Use YYYY-MM-DD",
            })

        async with ObsidianClient() as client:
            try:
                # Format content based on whether heading is specified
                if heading:
                    # If heading specified, we need to use PATCH
                    # For now, just prepend heading marker if not present
                    if not heading.startswith("#"):
                        heading = f"## {heading}"
                    append_content = f"\n{content}"

                    # Note: The periodic API may not support heading targeting
                    # Fall back to simple append with heading included
                    try:
                        await client.append_periodic(
                            f"\n\n{heading}\n\n{content}",
                            "daily",
                            date,
                        )
                    except ObsidianAPIError:
                        # Try simple append if heading-aware append fails
                        await client.append_periodic(append_content, "daily", date)
                else:
                    await client.append_periodic(f"\n{content}", "daily", date)

                return json.dumps({
                    "success": True,
                    "date": date,
                    "heading": heading,
                    "message": f"Appended to daily note for {date}",
                })
            except NoteNotFoundError:
                return json.dumps({
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Daily note not found for {date}. It may need to be created first.",
                })
            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

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
            return json.dumps({
                "error": True,
                "type": "ValidationError",
                "message": "Entry content cannot be empty",
            })

        # Use today if no date specified
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return json.dumps({
                "error": True,
                "type": "ValidationError",
                "message": f"Invalid date format: {date}. Use YYYY-MM-DD",
            })

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

        async with ObsidianClient() as client:
            try:
                await client.append_periodic(f"\n{entry}", "daily", date)

                return json.dumps({
                    "success": True,
                    "date": date,
                    "entry": entry,
                    "timestamp": timestamp,
                    "tags": tags,
                    "links": links,
                    "message": f"Created entry in daily note for {date}",
                })
            except NoteNotFoundError:
                return json.dumps({
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"Daily note not found for {date}. It may need to be created first.",
                })
            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

    @server.tool()
    async def get_periodic_note(
        period: str = "daily",
        date: str | None = None,
    ) -> str:
        """
        Get a periodic note (daily, weekly, monthly, quarterly, yearly).

        Requires the Periodic Notes plugin to be configured in Obsidian
        for non-daily periods.

        Args:
            period: Period type - "daily", "weekly", "monthly", "quarterly", "yearly"
            date: Optional date in appropriate format:
                  - daily: YYYY-MM-DD
                  - weekly: YYYY-MM-DD (uses week containing that date)
                  - monthly: YYYY-MM
                  - quarterly: YYYY-Q[1-4]
                  - yearly: YYYY

        Returns:
            JSON with periodic note content and metadata
        """
        valid_periods = ("daily", "weekly", "monthly", "quarterly", "yearly")
        if period not in valid_periods:
            return json.dumps({
                "error": True,
                "type": "ValidationError",
                "message": f"Invalid period: {period}. Must be one of: {', '.join(valid_periods)}",
            })

        # Default date handling
        if not date:
            today = datetime.now()
            if period in ("daily", "weekly"):
                date = today.strftime("%Y-%m-%d")
            elif period == "monthly":
                date = today.strftime("%Y-%m")
            elif period == "quarterly":
                quarter = (today.month - 1) // 3 + 1
                date = f"{today.year}-Q{quarter}"
            elif period == "yearly":
                date = str(today.year)

        async with ObsidianClient() as client:
            try:
                data = await client.get_periodic(period, date)

                return json.dumps({
                    "success": True,
                    "period": period,
                    "date": date,
                    "content": data.get("content", ""),
                    "tags": data.get("tags", []),
                    "frontmatter": data.get("frontmatter", {}),
                })
            except NoteNotFoundError:
                return json.dumps({
                    "error": True,
                    "type": "NoteNotFoundError",
                    "message": f"{period.capitalize()} note not found for {date}",
                })
            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })
