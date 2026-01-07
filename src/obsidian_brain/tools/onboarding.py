"""
Onboarding tools for Obsidian Brain MCP.

Provides tools for checking and performing vault onboarding, which includes
vault analysis and configuration generation.
"""

import json
from typing import TYPE_CHECKING

from ..cache import CacheNotInitializedError, vault_cache
from ..client import ObsidianAPIError, ObsidianClient
from ..onboarding import CONFIG_PATH, MEMORIES_PATH, onboarding_manager

if TYPE_CHECKING:
    from mcp_use.server import MCPServer


def register_onboarding_tools(server: "MCPServer") -> None:
    """Register all onboarding tools with the MCP server."""

    @server.tool()
    async def check_onboarding_status() -> str:
        """
        Check if this vault has been onboarded.

        Onboarding creates a `.obsidian-brain/` folder with:
        - config.yml: Vault profile and detected patterns
        - memories/: Persistent memory files for cross-session context

        Returns:
            JSON with onboarding status and recommendations:
            - onboarded: whether config exists
            - message: human-readable status
            - recommendation: suggested next action
        """
        async with ObsidianClient() as client:
            try:
                # List root to check for .obsidian-brain folder
                all_files = await client.get_all_files("/")

                status = onboarding_manager.check_onboarding_status(all_files)
                return json.dumps(status)

            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

    @server.tool()
    async def run_onboarding() -> str:
        """
        Perform vault onboarding to analyze structure and create configuration.

        This tool:
        1. Analyzes vault folder structure (PARA, Zettelkasten, etc.)
        2. Discovers tag conventions and hierarchies
        3. Identifies template patterns
        4. Examines frontmatter conventions
        5. Detects naming patterns

        Creates:
        - `.obsidian-brain/config.yml` - Vault profile and patterns
        - `.obsidian-brain/memories/vault-overview.md` - Structure overview
        - `.obsidian-brain/memories/conventions.md` - Usage guidelines

        **Prerequisites**: Call `refresh_vault_structure` first to populate the cache.

        Returns:
            JSON with:
            - success: whether onboarding completed
            - analysis_summary: detected patterns and conventions
            - files_created: list of created configuration files
        """
        # Check cache is initialized
        try:
            structure = vault_cache.get_structure()
        except CacheNotInitializedError:
            return json.dumps({
                "error": True,
                "type": "CacheNotInitializedError",
                "message": "Vault cache not initialized. Call refresh_vault_structure first.",
                "suggestion": "Run refresh_vault_structure before run_onboarding",
            })

        # Analyze the vault
        analysis = onboarding_manager.analyze_vault(structure)

        # Generate configuration and memories
        config_content = onboarding_manager.generate_config(analysis)
        overview_memory = onboarding_manager.generate_vault_overview_memory(analysis)
        conventions_memory = onboarding_manager.generate_conventions_memory(analysis)

        async with ObsidianClient() as client:
            try:
                files_created = []

                # Create config.yml
                await client.create_note(CONFIG_PATH, config_content)
                files_created.append(CONFIG_PATH)

                # Create vault-overview memory
                overview_path = f"{MEMORIES_PATH}/vault-overview.md"
                await client.create_note(overview_path, overview_memory)
                files_created.append(overview_path)

                # Create conventions memory
                conventions_path = f"{MEMORIES_PATH}/conventions.md"
                await client.create_note(conventions_path, conventions_memory)
                files_created.append(conventions_path)

                return json.dumps({
                    "success": True,
                    "message": "Vault onboarding completed successfully",
                    "analysis_summary": {
                        "organizational_systems": analysis.folder_patterns,
                        "folder_purposes": analysis.folder_purposes,
                        "tag_prefixes": analysis.tag_prefixes,
                        "tag_count": len(analysis.top_tags),
                        "templates_found": len(analysis.templates_found),
                        "naming_patterns": analysis.naming_patterns,
                        "common_frontmatter_keys": analysis.common_frontmatter_keys[:5],
                    },
                    "files_created": files_created,
                    "next_steps": [
                        "Review the generated config at .obsidian-brain/config.yml",
                        "Read memories with list_memories and read_memory",
                        "Create custom memories as you learn about the vault",
                    ],
                })

            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

    @server.tool()
    async def get_vault_config() -> str:
        """
        Get the vault configuration file content.

        The config file contains detected patterns and conventions from onboarding:
        - Organizational systems (PARA, Zettelkasten, etc.)
        - Tag conventions and hierarchies
        - Naming patterns
        - Frontmatter conventions
        - Template locations

        Returns:
            JSON with config content or error if not onboarded
        """
        async with ObsidianClient() as client:
            try:
                data = await client.get_note(CONFIG_PATH, include_metadata=False)
                content = data.get("content", "")

                return json.dumps({
                    "exists": True,
                    "path": CONFIG_PATH,
                    "content": content,
                })

            except Exception:
                return json.dumps({
                    "exists": False,
                    "path": CONFIG_PATH,
                    "message": "Vault not onboarded. Run run_onboarding first.",
                })
