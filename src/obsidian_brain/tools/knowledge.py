"""
Knowledge base tools for Obsidian Brain MCP.

Provides tools for generating and managing the persistent vault knowledge base.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..cache import CacheNotInitializedError, vault_cache
from ..exceptions import NoteNotFoundError, ObsidianCLIError
from ..knowledge import KNOWLEDGE_BASE_PATH, knowledge_manager

if TYPE_CHECKING:
    from ..protocol import VaultClient


def register_knowledge_tools(server, client: VaultClient) -> None:
    """Register all knowledge base tools with the MCP server."""

    @server.tool()
    async def create_vault_knowledge_base(
        include_orphans: bool = True,
        include_link_patterns: bool = True,
    ) -> str:
        """
        Generate or update the persistent vault knowledge base file.

        This creates a comprehensive Markdown file containing:
        - Vault folder structure tree
        - Tag taxonomy with usage counts
        - Hub notes (most connected)
        - Link patterns and relationships
        - Orphan notes list (optional)

        The file is stored at `.obsidian-brain/knowledge-base.md` in your vault
        and persists across sessions.

        **RECOMMENDED**: Call this tool on first use of the MCP server to establish
        context for future interactions. Regenerate when vault structure changes
        significantly.

        Args:
            include_orphans: Include list of orphan notes (default: True)
            include_link_patterns: Include link analysis section (default: True)

        Returns:
            JSON with success status, file path, and summary statistics
        """
        # Check cache is initialized
        try:
            structure = vault_cache.get_structure()
        except CacheNotInitializedError:
            return json.dumps({
                "error": True,
                "type": "CacheNotInitializedError",
                "message": "Vault cache not initialized. Call refresh_vault_structure first.",
                "suggestion": "Run refresh_vault_structure before create_vault_knowledge_base",
            })

        # Generate the knowledge base content
        content = knowledge_manager.generate_content(
            structure,
            include_orphans=include_orphans,
            include_link_patterns=include_link_patterns,
        )

        # Write to vault via VaultClient
        try:
            # Create or update the knowledge base file
            await client.create_note(KNOWLEDGE_BASE_PATH, content)

            return json.dumps({
                "success": True,
                "path": KNOWLEDGE_BASE_PATH,
                "message": f"Knowledge base created/updated at {KNOWLEDGE_BASE_PATH}",
                "stats": {
                    "total_notes": structure.stats.total_notes,
                    "total_folders": structure.stats.total_folders,
                    "total_tags": structure.stats.total_tags,
                    "total_links": structure.stats.total_links,
                    "orphan_notes": structure.stats.orphan_notes,
                },
                "sections_included": {
                    "orphans": include_orphans,
                    "link_patterns": include_link_patterns,
                },
            })
        except ObsidianCLIError as e:
            return json.dumps({
                "error": True,
                "type": "ObsidianCLIError",
                "message": str(e),
            })

    @server.tool()
    async def get_knowledge_base_status() -> str:
        """
        Check if the knowledge base exists and when it was last updated.

        Use this to determine if create_vault_knowledge_base should be called.

        Returns:
            JSON with:
            - exists: whether the knowledge base file exists
            - path: storage path in vault
            - recommendation: suggested action based on status
        """
        try:
            # Try to read the knowledge base
            data = await client.get_note(KNOWLEDGE_BASE_PATH, include_metadata=True)

            # Extract stats from frontmatter if available
            frontmatter = data.get("frontmatter", {})
            vault_stats = frontmatter.get("vault_stats", {})

            return json.dumps({
                "exists": True,
                "path": KNOWLEDGE_BASE_PATH,
                "created": frontmatter.get("created"),
                "updated": frontmatter.get("updated"),
                "generator": frontmatter.get("generator"),
                "vault_stats_at_generation": vault_stats,
                "recommendation": "Knowledge base exists. Regenerate if vault has changed significantly.",
            })
        except NoteNotFoundError:
            return json.dumps({
                "exists": False,
                "path": KNOWLEDGE_BASE_PATH,
                "recommendation": "Knowledge base not found. Call create_vault_knowledge_base to generate it.",
            })
        except ObsidianCLIError as e:
            return json.dumps({
                "error": True,
                "type": "ObsidianCLIError",
                "message": str(e),
            })
