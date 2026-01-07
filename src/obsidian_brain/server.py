"""
Obsidian Brain MCP Server

Main server module that initializes the MCP server and registers
all tools and resources.
"""

from mcp_use.server import MCPServer

from . import __version__
from .resources.knowledge import register_knowledge_resource
from .resources.structure import register_structure_resource
from .tools.daily import register_daily_tools
from .tools.knowledge import register_knowledge_tools
from .tools.links import register_link_tools
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

1. First, call `refresh_vault_structure` to initialize the vault cache
2. **RECOMMENDED**: Call `create_vault_knowledge_base` to generate persistent context
3. Use `list_vault_files` to explore the vault structure
4. Use `get_note` to read note content and metadata
5. Use `create_note` to create new notes with tags and backlinks

## Available Resources

- `vault://structure` - Full vault structure with folders, notes, and metadata (JSON)
- `vault://tags` - All tags with usage counts (JSON)
- `vault://stats` - Aggregate vault statistics (JSON)
- `vault://knowledge` - **Persistent knowledge base** (Markdown) - comprehensive vault overview

## Available Tools

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

### Knowledge Base (Persistent Context)
- `create_vault_knowledge_base` - Generate/update persistent vault knowledge file
- `get_knowledge_base_status` - Check if knowledge base exists and when updated

## Key Features

- **Persistent knowledge base**: LLM-readable vault overview stored in vault
- **Auto-generated titles**: Note titles are extracted from filenames
- **Backlink validation**: Links are verified to exist before creation
- **Frontmatter tags**: Tags are stored in YAML frontmatter
- **Wikilinks**: Links use Obsidian's [[wikilink]] format
- **Link traversal**: Explore note relationships up to 3 hops
- **Full-text search**: Search across all vault content
- **Daily notes**: Timestamped entries with tags and links

## Knowledge Base Workflow

For best results, generate the knowledge base on first use:
1. Call `refresh_vault_structure` to scan the vault
2. Call `create_vault_knowledge_base` to create the persistent knowledge file
3. Access via `vault://knowledge` resource in future sessions

The knowledge base is stored at `.obsidian-brain/knowledge-base.md` and provides:
- Folder structure tree
- Tag taxonomy with counts
- Hub notes (most connected)
- Link patterns
- Orphan notes list

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

# Register all resources
register_structure_resource(server)
register_knowledge_resource(server)


def main():
    """Run the MCP server."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
