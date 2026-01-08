"""
Memory manager for Obsidian Brain MCP.

Handles persistent memories stored as markdown files in .obsidian-brain/memories/
to enable cross-session context retention for LLMs.
"""

import re
from dataclasses import dataclass
from datetime import datetime

import yaml

from .onboarding import MEMORIES_PATH


@dataclass
class Memory:
    """Represents a single memory file."""

    name: str
    content: str
    frontmatter: dict
    created: str | None = None
    updated: str | None = None
    memory_type: str | None = None


class MemoryManager:
    """
    Manages persistent memories in the vault.

    Memories are markdown files stored in .obsidian-brain/memories/
    that persist across sessions. Each memory has:
    - A descriptive name (filename without .md)
    - YAML frontmatter with metadata
    - Markdown content body
    """

    def __init__(self):
        self.memories_path = MEMORIES_PATH

    def get_memory_path(self, name: str) -> str:
        """
        Get the full path for a memory file.

        Args:
            name: Memory name (without .md extension)

        Returns:
            Full path to memory file
        """
        # Sanitize name for filesystem
        safe_name = self._sanitize_name(name)
        return f"{self.memories_path}/{safe_name}.md"

    def _sanitize_name(self, name: str) -> str:
        """
        Sanitize memory name for use as filename.

        Args:
            name: Raw memory name

        Returns:
            Filesystem-safe name
        """
        # Remove .md extension if provided
        if name.endswith(".md"):
            name = name[:-3]
        # Replace spaces with hyphens, remove special chars
        safe = re.sub(r"[^\w\s-]", "", name)
        safe = re.sub(r"[\s_]+", "-", safe)
        return safe.lower().strip("-")

    def parse_memory(self, content: str, name: str) -> Memory:
        """
        Parse a memory file content into Memory object.

        Args:
            content: Raw file content
            name: Memory name

        Returns:
            Parsed Memory object
        """
        frontmatter: dict = {}
        body = content

        # Extract YAML frontmatter if present
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2].strip()
                except yaml.YAMLError:
                    # If YAML parsing fails, treat entire content as body
                    pass

        return Memory(
            name=name,
            content=body,
            frontmatter=frontmatter,
            created=frontmatter.get("created"),
            updated=frontmatter.get("updated"),
            memory_type=frontmatter.get("type"),
        )

    def create_memory_content(
        self,
        content: str,
        memory_type: str | None = None,
        extra_frontmatter: dict | None = None,
    ) -> str:
        """
        Create formatted memory content with frontmatter.

        Args:
            content: Memory body content
            memory_type: Optional type classification
            extra_frontmatter: Additional frontmatter fields

        Returns:
            Complete markdown content with frontmatter
        """
        now = datetime.now().isoformat()

        frontmatter: dict = {
            "created": now,
            "updated": now,
        }

        if memory_type:
            frontmatter["type"] = memory_type

        if extra_frontmatter:
            frontmatter.update(extra_frontmatter)

        yaml_content = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)

        return f"---\n{yaml_content}---\n\n{content}"

    def update_memory_content(self, existing_content: str, new_content: str) -> str:
        """
        Update memory content while preserving created date.

        Args:
            existing_content: Current file content
            new_content: New body content

        Returns:
            Updated markdown content
        """
        existing = self.parse_memory(existing_content, "temp")

        # Preserve original frontmatter, update timestamp
        frontmatter = existing.frontmatter.copy()
        frontmatter["updated"] = datetime.now().isoformat()

        yaml_content = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)

        return f"---\n{yaml_content}---\n\n{new_content}"

    def list_from_files(self, files: list[str]) -> list[dict]:
        """
        List all memories from a file listing.

        Args:
            files: List of file paths from vault

        Returns:
            List of memory info dicts with name and path
        """
        memories = []
        prefix = f"{self.memories_path}/"

        for path in files:
            if path.startswith(prefix) and path.endswith(".md"):
                name = path[len(prefix) : -3]  # Remove prefix and .md
                memories.append({
                    "name": name,
                    "path": path,
                })

        return memories

    def format_memory_list(self, memories: list[Memory]) -> str:
        """
        Format a list of memories for display.

        Args:
            memories: List of Memory objects

        Returns:
            Formatted string listing memories
        """
        if not memories:
            return "No memories found."

        lines = ["# Available Memories", ""]

        for memory in memories:
            type_str = f" [{memory.memory_type}]" if memory.memory_type else ""
            lines.append(f"- **{memory.name}**{type_str}")
            if memory.updated:
                lines.append(f"  - Updated: {memory.updated}")

        return "\n".join(lines)


# Global singleton instance
memory_manager = MemoryManager()
