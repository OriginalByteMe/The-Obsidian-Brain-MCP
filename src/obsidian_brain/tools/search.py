"""
Search tools for Obsidian Brain MCP.

Provides tools for searching vault content using simple text search.
"""

import json

from mcp.server.fastmcp import FastMCP

from ..models import SearchMatch
from ..protocol import VaultClient
from .errors import OPERATIONAL_ERRORS, error_json


def register_search_tools(server: FastMCP, client: VaultClient) -> None:
    """Register all search-related tools with the MCP server."""

    @server.tool()
    async def search_content(query: str) -> str:
        """
        Search for text across all notes in the vault.

        Performs full-text search and returns matching snippets with context.

        Args:
            query: Search query string (supports basic text matching)

        Returns:
            JSON object with normalized paths, context matches, and scores
            Failures return {"error": true, "type": "<exception>", "message": "<details>"}.
        """
        if not query or not query.strip():
            return json.dumps(
                {
                    "error": True,
                    "type": "ValidationError",
                    "message": "Search query cannot be empty",
                }
            )

        try:
            results = await client.search_simple(query)
            matches: list[dict[str, object]] = []
            total_matches = 0
            for result in results:
                match = SearchMatch.model_validate(result)
                matches.append(match.model_dump())
                total_matches += len(match.matches)

            return json.dumps(
                {
                    "success": True,
                    "query": query,
                    "results": matches,
                    "total_matches": total_matches,
                }
            )
        except OPERATIONAL_ERRORS as error:
            return error_json(error)
