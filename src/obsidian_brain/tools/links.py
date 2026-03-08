"""
Link operation tools for Obsidian Brain MCP.

Provides tools for managing wikilinks, backlinks, and link graph traversal.
"""

import json

from mcp.server.fastmcp import FastMCP

from ..cache import CacheNotInitializedError, vault_cache
from ..exceptions import NoteNotFoundError
from ..models import LinkGraph, LinkGraphEdge, LinkGraphNode
from ..protocol import VaultClient
from ..utils.wikilinks import contains_wikilink, extract_wikilinks, inject_wikilink


class InvalidBacklinkError(Exception):
    """Raised when a backlink target doesn't exist."""

    def __init__(self, target: str):
        self.target = target
        super().__init__(f"Backlink target does not exist: {target}")


def register_link_tools(server: FastMCP, client: VaultClient) -> None:
    """Register all link-related tools with the MCP server."""

    @server.tool()
    async def add_backlink(
        source_path: str,
        target_note: str,
        context: str = "",
    ) -> str:
        """
        Add a [[wikilink]] to target_note in the source note.

        The target note is validated to exist before adding the link.
        The link is added under a "See Also" section.

        Args:
            source_path: Path to note where link will be added
            target_note: Name of note to link to (without .md extension)
            context: Optional context text before the link

        Returns:
            Confirmation message

        Example:
            add_backlink("Projects/AI.md", "Research/Papers", "See also")
            # Adds: "- See also [[Research/Papers]]" to Projects/AI.md
        """
        # Validate target exists
        target_path = (
            target_note if target_note.endswith(".md") else f"{target_note}.md"
        )
        exists = await client.note_exists(target_path)

        if not exists:
            # Try without folder prefix
            simple_name = target_path.split("/")[-1]
            exists = await client.note_exists(simple_name)

        if not exists:
            return json.dumps({
                "error": True,
                "type": "InvalidBacklinkError",
                "message": f"Target note does not exist: {target_note}",
            })

        # Get source note content
        try:
            source_data = await client.get_note(source_path, include_metadata=False)
            content = source_data.get("content", "")
        except NoteNotFoundError:
            return json.dumps({
                "error": True,
                "type": "NoteNotFoundError",
                "message": f"Source note not found: {source_path}",
            })

        # Check if link already exists
        if contains_wikilink(content, target_note):
            return json.dumps({
                "error": True,
                "type": "LinkAlreadyExistsError",
                "message": f"Link to {target_note} already exists in {source_path}",
            })

        # Inject the wikilink
        new_content = inject_wikilink(content, target_note, context)

        # Update the note
        await client.update_note(source_path, new_content)

        return json.dumps({
            "success": True,
            "source": source_path,
            "target": target_note,
            "message": f"Added link to [[{target_note}]] in {source_path}",
        })

    @server.tool()
    async def get_backlinks(path: str) -> str:
        """
        Get all notes that contain links TO the specified note.

        Uses the cached vault structure for fast lookup.
        Call refresh_vault_structure first if cache is not initialized.

        Args:
            path: Path to the note

        Returns:
            JSON array of note paths that link to this note
        """
        try:
            backlinks = vault_cache.get_backlinks(path)
            return json.dumps({
                "success": True,
                "path": path,
                "backlinks": backlinks,
                "count": len(backlinks),
            })
        except CacheNotInitializedError:
            return json.dumps({
                "error": True,
                "type": "CacheNotInitializedError",
                "message": "Vault cache not initialized. Call refresh_vault_structure first.",
            })

    @server.tool()
    async def get_outgoing_links(path: str) -> str:
        """
        Get all notes that the specified note links TO.

        Extracts [[wikilinks]] from the note content.

        Args:
            path: Path to the note

        Returns:
            JSON array of linked note names/paths
        """
        try:
            data = await client.get_note(path, include_metadata=False)
            content = data.get("content", "")
            links = extract_wikilinks(content)

            return json.dumps({
                "success": True,
                "path": path,
                "outgoing_links": links,
                "count": len(links),
            })
        except NoteNotFoundError:
            return json.dumps({
                "error": True,
                "type": "NoteNotFoundError",
                "message": f"Note not found: {path}",
            })

    @server.tool()
    async def get_linked_notes(
        path: str,
        depth: int = 1,
        direction: str = "both",
    ) -> str:
        """
        Traverse the link graph starting from a note.

        Returns a subgraph of connected notes with edges showing relationships.

        Args:
            path: Starting note path
            depth: How many hops to traverse (1-3, default 1)
            direction: "incoming" (backlinks), "outgoing", or "both"

        Returns:
            JSON object with nodes and edges representing the subgraph
        """
        # Validate parameters
        depth = max(1, min(3, depth))  # Clamp to 1-3
        if direction not in ("incoming", "outgoing", "both"):
            direction = "both"

        try:
            # Check cache is initialized
            if not vault_cache.is_initialized:
                return json.dumps({
                    "error": True,
                    "type": "CacheNotInitializedError",
                    "message": "Vault cache not initialized. Call refresh_vault_structure first.",
                })

            # BFS traversal
            visited: set[str] = set()
            nodes: list[LinkGraphNode] = []
            edges: list[LinkGraphEdge] = []
            queue: list[tuple[str, int]] = [(path, 0)]

            while queue:
                current_path, current_depth = queue.pop(0)

                if current_path in visited:
                    continue

                visited.add(current_path)
                nodes.append(LinkGraphNode(path=current_path, depth=current_depth))

                if current_depth >= depth:
                    continue

                # Get note metadata from cache
                note_meta = vault_cache.get_note_metadata(current_path)

                if note_meta is None:
                    continue

                # Collect connected notes based on direction
                if direction in ("outgoing", "both"):
                    for link in note_meta.outgoing_links:
                        # Resolve link to path
                        resolved = _resolve_link_to_path(link)
                        if resolved and resolved not in visited:
                            edges.append(LinkGraphEdge(
                                source=current_path,
                                target=resolved,
                            ))
                            queue.append((resolved, current_depth + 1))

                if direction in ("incoming", "both"):
                    for backlink_path in note_meta.incoming_links:
                        if backlink_path not in visited:
                            edges.append(LinkGraphEdge(
                                source=backlink_path,
                                target=current_path,
                            ))
                            queue.append((backlink_path, current_depth + 1))

            graph = LinkGraph(
                center=path,
                nodes=nodes,
                edges=edges,
            )

            return graph.model_dump_json(indent=2)

        except CacheNotInitializedError:
            return json.dumps({
                "error": True,
                "type": "CacheNotInitializedError",
                "message": "Vault cache not initialized. Call refresh_vault_structure first.",
            })


def _resolve_link_to_path(link: str) -> str | None:
    """
    Resolve a wikilink target to a full path using the cache.

    Returns None if the note cannot be found.
    """
    if not vault_cache.is_initialized:
        return None

    structure = vault_cache.get_structure()

    # Build a lookup map
    name_to_path: dict[str, str] = {}
    for note in structure.notes:
        # Map by full path
        name_to_path[note.path.lower()] = note.path

        # Map by path without .md
        path_no_ext = note.path[:-3] if note.path.endswith(".md") else note.path
        name_to_path[path_no_ext.lower()] = note.path

        # Map by filename only
        filename = note.path.split("/")[-1]
        if filename.endswith(".md"):
            filename = filename[:-3]
        name_to_path[filename.lower()] = note.path

    # Try to resolve
    link_lower = link.lower()

    # Exact match
    if link_lower in name_to_path:
        return name_to_path[link_lower]

    # With .md extension
    if f"{link_lower}.md" in name_to_path:
        return name_to_path[f"{link_lower}.md"]

    # Just the name part
    link_name = link.split("/")[-1].lower()
    if link_name in name_to_path:
        return name_to_path[link_name]

    return None
