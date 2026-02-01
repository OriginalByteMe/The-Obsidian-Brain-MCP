"""
Obsidian Brain MCP Server

Main server module that initializes the MCP server and registers
all tools and resources.
"""

from mcp_use.server import MCPServer

from . import __version__
from .resources.knowledge import register_knowledge_resource
from .resources.structure import register_structure_resource
from .resources.vault_access import register_vault_access_resources
from .tools.daily import register_daily_tools
from .tools.knowledge import register_knowledge_tools
from .tools.links import register_link_tools
from .tools.memory import register_memory_tools
from .tools.onboarding import register_onboarding_tools
from .tools.search import register_search_tools
from .tools.tags import register_tag_tools
from .tools.vault import register_vault_tools

# Initialize the MCP server
server = MCPServer(
    name="obsidian-brain",
    version=__version__,
    instructions="""
Obsidian Brain MCP Server - Intelligent Obsidian Vault Interaction

This server provides tools for interacting with your Obsidian vault through
the Obsidian Local REST API.

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
- `vault://note/{path}` - Read a specific note by path (e.g., vault://note/Projects/MyNote.md)
- `vault://folder/{path}` - List all notes in a folder recursively (e.g., vault://folder/Projects)

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
- `search_advanced` - Dataview DQL query (requires plugin)
- `search_jsonlogic` - JsonLogic query for complex filtering

### Daily/Periodic Notes
- `get_daily_note` - Get today's or specific date's daily note
- `append_to_daily` - Append content to daily note
- `create_daily_entry` - Create timestamped entry with tags/links
- `get_periodic_note` - Get weekly/monthly/quarterly/yearly notes

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

## Configuration

Set these environment variables:
- OBSIDIAN_API_KEY: Your API key from Obsidian Local REST API plugin
- OBSIDIAN_HOST: API host (default: 127.0.0.1)
- OBSIDIAN_PORT: API port (default: 27124)
""".strip(),
)

# Register all tools
register_vault_tools(server)
register_link_tools(server)
register_tag_tools(server)
register_search_tools(server)
register_daily_tools(server)
register_knowledge_tools(server)
register_onboarding_tools(server)
register_memory_tools(server)

# Register all resources
register_structure_resource(server)
register_knowledge_resource(server)
register_vault_access_resources(server)


def main():
    """Run the MCP server."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
