"""
Knowledge base resource for Obsidian Brain MCP.

Exposes the persistent knowledge base file as an MCP resource.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import NoteNotFoundError, ObsidianCLIError
from ..knowledge import KNOWLEDGE_BASE_PATH

if TYPE_CHECKING:
    from ..protocol import VaultClient


def register_knowledge_resource(server, client: VaultClient) -> None:
    """Register the knowledge base resource with the MCP server."""

    @server.resource("vault://knowledge")
    async def vault_knowledge() -> str:
        """
        Returns the persistent vault knowledge base content.

        This is a comprehensive Markdown document containing:
        - Vault structure overview
        - Folder hierarchy tree
        - Tag taxonomy with usage counts
        - Hub notes (most connected)
        - Link patterns
        - Orphan notes

        Unlike vault://structure (JSON), this is a human-readable Markdown
        document designed for LLM consumption and persisted across sessions.

        If the knowledge base hasn't been generated yet, returns a helpful
        message explaining how to create it.

        Returns:
            Markdown content of the knowledge base, or instructions if not found
        """
        try:
            data = await client.get_note(KNOWLEDGE_BASE_PATH)
            return data.get("content", "")
        except NoteNotFoundError:
            return f"""# Knowledge Base Not Found

The vault knowledge base has not been generated yet.

## How to Create It

1. First, call the `refresh_vault_structure` tool to scan your vault
2. Then, call the `create_vault_knowledge_base` tool to generate this file

The knowledge base will be created at: `{KNOWLEDGE_BASE_PATH}`

## What It Contains

Once generated, the knowledge base provides:
- **Folder Structure**: Visual tree of your vault organization
- **Tag Taxonomy**: All tags with usage counts and examples
- **Hub Notes**: Most connected notes in your vault
- **Link Patterns**: Notes with most backlinks and outgoing links
- **Orphan Notes**: Unconnected notes that may need attention

This file persists across sessions, so you only need to regenerate it
when your vault structure changes significantly.
"""
        except ObsidianCLIError as e:
            return f"""# Error Reading Knowledge Base

An error occurred while reading the knowledge base:

```
{e}
```

Try regenerating it with `create_vault_knowledge_base`.
"""
