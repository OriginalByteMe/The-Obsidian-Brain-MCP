"""
Obsidian Brain MCP Server

Main server module that initializes the MCP server and registers
all tools and resources.
"""

from mcp_use.server import MCPServer

from . import __version__
from .resources.structure import register_structure_resource
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
2. Use `list_vault_files` to explore the vault structure
3. Use `get_note` to read note content and metadata
4. Use `create_note` to create new notes with tags and backlinks

## Available Resources

- `vault://structure` - Full vault structure with folders, notes, and metadata
- `vault://tags` - All tags with usage counts
- `vault://stats` - Aggregate vault statistics

## Key Features

- **Auto-generated titles**: Note titles are extracted from filenames
- **Backlink validation**: Links are verified to exist before creation
- **Frontmatter tags**: Tags are stored in YAML frontmatter
- **Wikilinks**: Links use Obsidian's [[wikilink]] format

## Configuration

Set these environment variables:
- OBSIDIAN_API_KEY: Your API key from Obsidian Local REST API plugin
- OBSIDIAN_HOST: API host (default: 127.0.0.1)
- OBSIDIAN_PORT: API port (default: 27124)
""".strip(),
)

# Register all tools
register_vault_tools(server)

# Register all resources
register_structure_resource(server)


def main():
    """Run the MCP server."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
