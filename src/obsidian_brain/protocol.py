"""
VaultClient Protocol for Obsidian Brain MCP.

Defines the async interface that all vault backend implementations must satisfy.
Uses structural typing (Protocol) so implementations don't need to inherit.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VaultClient(Protocol):
    """Async interface for vault operations.

    All vault backends must implement these methods. Uses structural
    typing -- implementations satisfy the protocol by having matching
    method signatures, no inheritance required.

    Methods map to Obsidian CLI commands:
        list_directory  -> obsidian files folder="{path}" format=json
        get_all_files   -> obsidian files ext=md format=json
        get_note        -> obsidian read path="{path}" format=json
        note_exists     -> obsidian read (check returncode)
        create_note     -> obsidian create name="{name}" path="{folder}" content="{content}" --silent
        update_note     -> obsidian create --overwrite --silent
        append_to_note  -> obsidian append file="{name}" content="{content}"
        delete_note     -> obsidian delete file="{name}"
        search_simple   -> obsidian search query="{query}" format=json
        get_daily_note  -> obsidian daily:read format=json
        append_daily    -> obsidian daily:append content="{content}"
    """

    async def list_directory(self, path: str = "/") -> list[dict[str, Any]]:
        """List files and folders at the specified path.

        Args:
            path: Relative path in vault (default: root "/").

        Returns:
            List of dicts with 'name' and 'type' ('file' or 'folder') keys.
        """
        ...

    async def get_all_files(self, path: str = "/") -> list[str]:
        """Get all file paths under a directory.

        Args:
            path: Starting path (default: root).

        Returns:
            List of all file paths relative to vault root.
        """
        ...

    async def get_note(self, path: str) -> dict[str, Any]:
        """Get a note's content and metadata.

        Args:
            path: Path to the note (e.g., "Projects/MyProject.md").

        Returns:
            Dict with path, content, raw, tags, frontmatter, and modified.
            ``raw`` is the complete original text, including YAML frontmatter.
        """
        ...

    async def note_exists(self, path: str) -> bool:
        """Check if a note exists in the vault.

        Args:
            path: Path to check.

        Returns:
            True if note exists, False otherwise.
        """
        ...

    async def create_note(self, path: str, content: str) -> None:
        """Create a new note.

        Args:
            path: Path for the note.
            content: Full note content including frontmatter.
        """
        ...

    async def update_note(self, path: str, content: str) -> None:
        """Replace a note's entire content.

        Args:
            path: Path to the note.
            content: New content (replaces everything).
        """
        ...

    async def append_to_note(self, path: str, content: str) -> None:
        """Append content to an existing note.

        Args:
            path: Path to the note.
            content: Content to append.
        """
        ...

    async def delete_note(self, path: str) -> None:
        """Delete a note from the vault.

        Args:
            path: Path to the note to delete.
        """
        ...

    async def search_simple(self, query: str) -> list[dict[str, Any]]:
        """Perform text search across the vault.

        Args:
            query: Search query string.

        Returns:
            List of matches with path, matches, and score.
        """
        ...

    async def get_daily_path(self, date: str | None = None) -> str:
        """Resolve the daily note's vault-relative path, created or not.

        Args:
            date: Optional date string for a specific daily note.

        Returns:
            Vault-relative path of the daily note.
        """
        ...

    async def get_daily_note(self, date: str | None = None) -> dict[str, Any]:
        """Get today's daily note (or a specific date's).

        Args:
            date: Optional date string (e.g., "2026-03-08").

        Returns:
            Dict with content, tags, frontmatter.
        """
        ...

    async def append_daily(self, content: str, date: str | None = None) -> None:
        """Append content to today's daily note.

        Args:
            content: Content to append.
            date: Optional date string for a specific daily note.
        """
        ...
