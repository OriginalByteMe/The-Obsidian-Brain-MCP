"""Knowledge base tool: a generated whole-vault overview kept in `Obsidian Brain/`."""

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from ..knowledge import KNOWLEDGE_BASE_PATH, VaultStats, compute_stats, render_knowledge_base
from ..memory import utc_now
from ..vault import get_vault
from .notes import DESTRUCTIVE


class KnowledgeBaseBuilt(BaseModel):
    path: str
    action: Literal["created", "updated"]
    created: str = Field(description="When the file was first generated (kept across rebuilds).")
    updated: str = Field(description="When this version was generated (UTC).")
    stats: VaultStats


def register(server: MCPServer) -> None:
    @server.tool(annotations=DESTRUCTIVE)
    async def build_knowledge_base(
        include_orphans: Annotated[
            bool, Field(description="Add a section listing notes with no links in or out.")
        ] = True,
        include_link_patterns: Annotated[
            bool, Field(description="Add sections on the most linked-to and most linking notes.")
        ] = True,
    ) -> KnowledgeBaseBuilt:
        """Generate (or regenerate) the vault overview at Obsidian Brain/knowledge-base.md.

        The file holds the folder tree, tag taxonomy, hub notes, link patterns and orphans, and
        replaces any previous version (its `created` date is kept). Obsidian Brain/ itself is
        left out of the numbers. Read it back with the vault://knowledge resource;
        get_vault_config says whether it exists. Use run_onboarding for the conventions profile.
        Example: build_knowledge_base(include_orphans=false)
        """
        vault = get_vault()
        snapshot = await vault.snapshot()
        previous = next((n for n in snapshot.notes if n.path == KNOWLEDGE_BASE_PATH), None)
        now = utc_now()
        created = str(previous.frontmatter.get("created") or now) if previous else now
        text = render_knowledge_base(
            snapshot,
            created=created,
            now=now,
            include_orphans=include_orphans,
            include_link_patterns=include_link_patterns,
        )
        await vault.write_note(KNOWLEDGE_BASE_PATH, text, overwrite=True)
        return KnowledgeBaseBuilt(
            path=KNOWLEDGE_BASE_PATH,
            action="updated" if previous else "created",
            created=created,
            updated=now,
            stats=compute_stats(snapshot),
        )
