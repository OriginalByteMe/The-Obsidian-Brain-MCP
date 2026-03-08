"""
Search tools for Obsidian Brain MCP.

Provides tools for searching vault content using simple text search.
"""

import json

from mcp.server.fastmcp import FastMCP

from ..exceptions import ObsidianCLIError
from ..models import SearchMatch
from ..protocol import VaultClient


def register_search_tools(server: FastMCP, client: VaultClient) -> None:
    """Register all search-related tools with the MCP server."""

    @server.tool()
    async def search_content(
        query: str,
        context_length: int = 100,
    ) -> str:
        """
        Search for text across all notes in the vault.

        Performs full-text search and returns matching snippets with context.

        Args:
            query: Search query string (supports basic text matching)
            context_length: Characters of context around matches (default 100)

        Returns:
            JSON array of matches with file paths, snippets, and scores
        """
        if not query or not query.strip():
            return json.dumps({
                "error": True,
                "type": "ValidationError",
                "message": "Search query cannot be empty",
            })

        try:
            results = await client.search_simple(query, context_length)

            # Format results consistently
            matches = []
            for result in results:
                # Handle different response formats from the CLI
                if isinstance(result, dict):
                    path = result.get("filename", result.get("path", ""))
                    snippets = result.get("matches", [])
                    score = result.get("score", 0.0)

                    # Extract text from match objects if needed
                    match_texts = []
                    for m in snippets:
                        if isinstance(m, dict):
                            match_texts.append(m.get("match", str(m)))
                        else:
                            match_texts.append(str(m))

                    matches.append(SearchMatch(
                        path=path,
                        matches=match_texts,
                        score=score,
                    ).model_dump())

            return json.dumps({
                "success": True,
                "query": query,
                "results": matches,
                "total_matches": len(matches),
            })
        except ObsidianCLIError as e:
            return json.dumps({
                "error": True,
                "type": "ObsidianCLIError",
                "message": str(e),
            })
