"""
Memory tools for Obsidian Brain MCP.

Provides tools for managing persistent memories that store cross-session
context about the vault.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..cache import vault_cache
from ..exceptions import NoteNotFoundError
from ..memory import memory_manager
from ..onboarding import MEMORIES_PATH
from .errors import OPERATIONAL_ERRORS, error_json

if TYPE_CHECKING:
    from ..protocol import VaultClient


def register_memory_tools(server, client: VaultClient) -> None:
    """Register all memory tools with the MCP server."""

    @server.tool()
    async def list_memories() -> str:
        """
        List all available memories in the vault.

        Memories are persistent markdown files stored in `.obsidian-brain/memories/`
        that provide cross-session context.

        Returns:
            JSON array of memory objects with:
            - name: memory identifier (filename without .md)
            - path: full path in vault
            - type: memory type from frontmatter (if set)
            - updated: last update timestamp (if available)
        """
        try:
            # List all files in memories folder
            all_files = await client.get_all_files("/")
            memory_files = memory_manager.list_from_files(all_files)

            # Get metadata for each memory
            memories = []
            for mem_info in memory_files:
                try:
                    data = await client.get_note(mem_info["path"], include_metadata=True)
                    frontmatter = data.get("frontmatter", {})
                    memories.append(
                        {
                            "name": mem_info["name"],
                            "path": mem_info["path"],
                            "type": frontmatter.get("type"),
                            "created": frontmatter.get("created"),
                            "updated": frontmatter.get("updated"),
                        }
                    )
                except NoteNotFoundError:
                    # Skip if file was deleted between listing and reading
                    pass

            return json.dumps(
                {
                    "count": len(memories),
                    "memories": memories,
                    "memories_path": MEMORIES_PATH,
                }
            )

        except OPERATIONAL_ERRORS as error:
            return error_json(error)

    @server.tool()
    async def read_memory(name: str) -> str:
        """
        Read the content of a specific memory.

        Use this tool to retrieve context stored in previous sessions.
        Only read memories that are relevant to the current task.

        Args:
            name: Memory name (e.g., "vault-overview", "conventions")

        Returns:
            JSON with memory content and metadata
        """
        path = memory_manager.get_memory_path(name)

        try:
            data = await client.get_note(path, include_metadata=True)
            content = data.get("content", "")
            frontmatter = data.get("frontmatter", {})

            # Parse the memory
            memory = memory_manager.parse_memory(
                f"---\n{_format_frontmatter(frontmatter)}---\n\n{content}",
                name,
            )

            return json.dumps(
                {
                    "name": name,
                    "path": path,
                    "content": memory.content,
                    "type": memory.memory_type,
                    "created": memory.created,
                    "updated": memory.updated,
                    "frontmatter": frontmatter,
                }
            )

        except NoteNotFoundError:
            return json.dumps(
                {
                    "error": True,
                    "type": "MemoryNotFoundError",
                    "message": f"Memory '{name}' not found",
                    "path": path,
                    "suggestion": "Use list_memories to see available memories",
                }
            )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)

    @server.tool()
    async def write_memory(
        name: str,
        content: str,
        memory_type: str | None = None,
    ) -> str:
        """
        Create or update a memory with the given content.

        Use this to store useful information about the vault for future sessions.
        Good memory candidates:
        - Project context and goals
        - User preferences discovered during conversation
        - Important patterns or conventions not in initial analysis
        - Session summaries and learnings

        Args:
            name: Memory name (will be sanitized for filesystem)
            content: Markdown content for the memory body
            memory_type: Optional type classification (e.g., "project", "preference", "learning")

        Returns:
            JSON with success status and file path
        """
        path = memory_manager.get_memory_path(name)

        try:
            # Check if memory already exists
            try:
                existing = await client.get_note(path, include_metadata=False)
                existing_content = existing.get("raw", existing.get("content", ""))
                # Update existing memory
                full_content = memory_manager.update_memory_content(existing_content, content)
                action = "updated"
            except NoteNotFoundError:
                # Create new memory
                full_content = memory_manager.create_memory_content(
                    content, memory_type=memory_type
                )
                action = "created"

            await client.create_note(path, full_content)

            if vault_cache.is_initialized:
                await vault_cache.sync_note(client, path)

            return json.dumps(
                {
                    "success": True,
                    "action": action,
                    "name": name,
                    "path": path,
                    "message": f"Memory '{name}' {action} successfully",
                }
            )

        except OPERATIONAL_ERRORS as error:
            return error_json(error)

    @server.tool()
    async def delete_memory(name: str) -> str:
        """
        Delete a memory from the vault.

        Use this when a memory is no longer relevant or contains outdated information.

        Args:
            name: Memory name to delete

        Returns:
            JSON with success status
        """
        path = memory_manager.get_memory_path(name)

        try:
            await client.delete_note(path)

            if vault_cache.is_initialized:
                vault_cache.invalidate_path(path, exists=False)

            return json.dumps(
                {
                    "success": True,
                    "name": name,
                    "path": path,
                    "message": f"Memory '{name}' deleted successfully",
                }
            )

        except NoteNotFoundError:
            return json.dumps(
                {
                    "error": True,
                    "type": "MemoryNotFoundError",
                    "message": f"Memory '{name}' not found",
                    "path": path,
                }
            )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)

    @server.tool()
    async def edit_memory(
        name: str,
        search: str,
        replace: str,
        mode: str = "literal",
    ) -> str:
        """
        Edit a memory by replacing content matching a pattern.

        Args:
            name: Memory name to edit
            search: String or regex pattern to search for
            replace: Replacement string
            mode: "literal" for exact string match, "regex" for regex pattern

        Returns:
            JSON with success status and number of replacements
        """
        import re

        path = memory_manager.get_memory_path(name)

        try:
            data = await client.get_note(path, include_metadata=False)
            content = data.get("content", "")
            raw_content = data.get("raw", content)

            if mode == "regex":
                try:
                    pattern = re.compile(search, re.DOTALL | re.MULTILINE)
                    new_content, count = pattern.subn(replace, content)
                except re.error as e:
                    return json.dumps(
                        {
                            "error": True,
                            "type": "RegexError",
                            "message": f"Invalid regex pattern: {e}",
                        }
                    )
            else:
                count = content.count(search)
                new_content = content.replace(search, replace)

            if count == 0:
                return json.dumps(
                    {
                        "success": False,
                        "message": "Pattern not found in memory",
                        "name": name,
                    }
                )

            # Update the memory with new content
            full_content = memory_manager.update_memory_content(raw_content, new_content)
            await client.create_note(path, full_content)

            if vault_cache.is_initialized:
                await vault_cache.sync_note(client, path)

            return json.dumps(
                {
                    "success": True,
                    "name": name,
                    "path": path,
                    "replacements": count,
                    "message": f"Made {count} replacement(s) in memory '{name}'",
                }
            )

        except NoteNotFoundError:
            return json.dumps(
                {
                    "error": True,
                    "type": "MemoryNotFoundError",
                    "message": f"Memory '{name}' not found",
                    "path": path,
                }
            )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)


def _format_frontmatter(frontmatter: dict) -> str:
    """Format frontmatter dict as YAML string."""
    import yaml

    return yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
