"""
Obsidian Brain MCP Server

Main server module that initializes the FastMCP server and registers
all tools and resources.
"""

from mcp.server.fastmcp import FastMCP

from .cli_client import ObsidianCLIClient
from .resources.knowledge import register_knowledge_resource
from .resources.structure import register_structure_resource
from .tools.daily import register_daily_tools
from .tools.knowledge import register_knowledge_tools
from .tools.links import register_link_tools
from .tools.memory import register_memory_tools
from .tools.onboarding import register_onboarding_tools
from .tools.search import register_search_tools
from .tools.tags import register_tag_tools
from .tools.vault import register_vault_tools

# Initialize the MCP server
mcp = FastMCP(
    "obsidian-brain",
    instructions="""
Obsidian Brain MCP Server - Intelligent Obsidian Vault Interaction

This server provides tools for interacting with your Obsidian vault through
the Obsidian CLI (requires Obsidian 1.12+ with CLI enabled and on PATH).

## Getting Started

1. First, call `check_onboarding_status` to see if vault is initialized
2. If not onboarded, call `refresh_vault_structure` then `run_onboarding`
3. Use `list_memories` to see available context from previous sessions
4. Read relevant memories with `read_memory` before starting work
5. Use vault tools to explore and modify notes

## Onboarding Workflow

For new vaults or first-time use:
1. `check_onboarding_status` - Check if vault is configured
2. `refresh_vault_structure` - Scan the vault structure
3. `run_onboarding` - Analyze vault and create configuration

Onboarding creates `.obsidian-brain/` folder with:
- `config.yml` - Detected patterns (PARA, Zettelkasten, naming conventions)
- `memories/vault-overview.md` - Vault structure summary
- `memories/conventions.md` - Usage guidelines

## Memory System

Memories persist across sessions in `.obsidian-brain/memories/`:
- `list_memories` - See all available memories
- `read_memory` - Read specific memory content
- `write_memory` - Store new information for future sessions
- `edit_memory` - Modify existing memory content
- `delete_memory` - Remove outdated memories

Store memories for: project context, user preferences, learnings, session summaries.

## Available Resources

- `vault://structure` - Full vault structure with folders, notes, and metadata
- `vault://tags` - All tags with usage counts
- `vault://stats` - Aggregate vault statistics
- `vault://knowledge` - Persistent knowledge base (Markdown)

## Available Tools

### Onboarding & Memory
- `check_onboarding_status` - Check if vault is initialized
- `run_onboarding` - Analyze vault and create configuration
- `get_vault_config` - Read the vault configuration
- `list_memories` - List all stored memories
- `read_memory` - Read a specific memory
- `write_memory` - Create or update a memory
- `edit_memory` - Edit memory with search/replace
- `delete_memory` - Remove a memory

### Vault Operations
- `list_vault_files` - List files/folders at a path
- `get_note` - Read note content and metadata
- `create_note` - Create note with tags and backlinks
- `update_note` - Replace note content
- `append_to_note` - Append to note (optional heading target)
- `delete_note` - Delete a note
- `refresh_vault_structure` - Rebuild vault cache

### Link Operations
- `add_backlink` - Add [[wikilink]] to a note
- `get_backlinks` - Get notes linking TO a note
- `get_outgoing_links` - Get notes a note links TO
- `get_linked_notes` - Traverse link graph (depth 1-3)

### Tag Operations
- `add_tags` - Add tags to note frontmatter
- `remove_tags` - Remove tags from frontmatter
- `list_all_tags` - Get all tags with counts
- `get_notes_by_tag` - Find notes with specific tag

### Search Operations
- `search_content` - Full-text search across vault

### Daily Notes
- `get_daily_note` - Get today's or specific date's daily note
- `append_to_daily` - Append content to daily note
- `create_daily_entry` - Create timestamped entry with tags/links

### Knowledge Base
- `create_vault_knowledge_base` - Generate persistent vault overview
- `get_knowledge_base_status` - Check knowledge base status

## Key Features

- **Onboarding**: Auto-detect vault patterns (PARA, Zettelkasten, etc.)
- **Persistent memories**: Cross-session context storage
- **Knowledge base**: Comprehensive vault overview for LLM context
- **Backlink validation**: Links verified before creation
- **Frontmatter tags**: Tags stored in YAML frontmatter
- **Link traversal**: Explore relationships up to 3 hops
- **Full-text search**: Search across all vault content

## Requirements

- Obsidian 1.12+ with CLI enabled (Settings > General > Command line interface)
- CLI registered on PATH (click 'Register CLI' in Obsidian settings)
- Or set OBSIDIAN_CLI_PATH environment variable
""".strip(),
)

# Create the CLI client singleton
client = ObsidianCLIClient()

# Register core tools (migrated to VaultClient)
register_vault_tools(mcp, client)
register_link_tools(mcp, client)
register_tag_tools(mcp, client)
register_search_tools(mcp, client)
register_daily_tools(mcp, client)

# Register non-core tools
register_knowledge_tools(mcp, client)
register_onboarding_tools(mcp, client)
register_memory_tools(mcp, client)

# Register all resources
register_structure_resource(mcp)
register_knowledge_resource(mcp, client)


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
