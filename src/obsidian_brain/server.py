"""MCP server entry point: builds the server, registers tools and resources, runs stdio."""

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase

from . import __version__, resources
from .tools import daily, knowledge, memory, notes, onboarding

INSTRUCTIONS = """\
Obsidian Brain reads and writes an Obsidian vault through the running Obsidian app.

Prerequisites: Obsidian is open with the target vault loaded, "Command line interface" is
enabled (Settings > General > Advanced), and OBSIDIAN_VAULT names the vault (otherwise the
CLI's default vault is used).

Start with get_vault_config: it reports onboarding state, the knowledge base and the vault
configuration.

Paths are vault-relative with forward slashes, e.g. "Projects/Plan.md". Writing a path whose
suffix is not a file type Obsidian opens adds ".md". Content is stored exactly as given: nothing
is added to it, and existing notes are only replaced when overwrite=true. Deleting moves to the
trash unless permanent=true. One call carries at most about 900 KB of text.
"""

# Tool arguments are validated by models built on ArgModelBase, which ignores unknown keys: a
# misspelled `heading` would silently append at the end of the note. Forbidding them (set before
# any tool is registered) turns that into an error and `additionalProperties: false` in the schema.
ArgModelBase.model_config["extra"] = "forbid"

server = MCPServer("obsidian-brain", version=__version__, instructions=INSTRUCTIONS)

for module in (notes, daily, memory, onboarding, knowledge, resources):
    module.register(server)


def main() -> None:
    """Run the MCP server over stdio."""
    server.run("stdio")


if __name__ == "__main__":
    main()
