"""
Vault structure resource for Obsidian Brain MCP.

Exposes the cached vault structure as an MCP resource.
"""

from typing import TYPE_CHECKING

from ..cache import CacheNotInitializedError, vault_cache

if TYPE_CHECKING:
    from mcp_use.server import MCPServer


def register_structure_resource(server: "MCPServer") -> None:
    """Register the vault structure resource with the MCP server."""

    @server.resource(uri="vault://structure", mime_type="application/json")
    def vault_structure() -> str:
        """
        Returns the cached vault structure including folders, notes with metadata,
        and aggregate statistics.

        The structure includes:
        - folders: Hierarchical folder tree
        - notes: List of all notes with tags, links, frontmatter
        - stats: Aggregate statistics (counts, orphans)
        - refreshed_at: When the cache was last updated

        Use the refresh_vault_structure tool to update this resource.

        Returns:
            JSON representation of VaultStructure model

        Raises:
            CacheNotInitializedError: If refresh_vault_structure hasn't been called
        """
        try:
            structure = vault_cache.get_structure()
            return structure.model_dump_json(indent=2)
        except CacheNotInitializedError:
            return '{"error": "Vault structure not initialized. Call refresh_vault_structure tool first."}'

    @server.resource(uri="vault://tags", mime_type="application/json")
    def vault_tags() -> str:
        """
        Returns all tags used in the vault with their usage counts.

        Use the refresh_vault_structure tool to update this data.

        Returns:
            JSON object mapping tag names to counts
        """
        try:
            tags = vault_cache.get_all_tags()
            import json
            return json.dumps(tags, indent=2)
        except CacheNotInitializedError:
            return '{"error": "Vault structure not initialized. Call refresh_vault_structure tool first."}'

    @server.resource(uri="vault://stats", mime_type="application/json")
    def vault_stats() -> str:
        """
        Returns aggregate statistics about the vault.

        Includes:
        - total_notes: Number of markdown files
        - total_folders: Number of directories
        - total_tags: Number of unique tags
        - total_links: Number of wikilinks
        - orphan_notes: Notes with no links

        Returns:
            JSON representation of VaultStats model
        """
        try:
            structure = vault_cache.get_structure()
            return structure.stats.model_dump_json(indent=2)
        except CacheNotInitializedError:
            return '{"error": "Vault structure not initialized. Call refresh_vault_structure tool first."}'
