"""
Search tools for Obsidian Brain MCP.

Provides tools for searching vault content using simple text search
and Dataview DQL queries.
"""

import json
from typing import TYPE_CHECKING

from ..client import ObsidianAPIError, ObsidianClient
from ..models import SearchMatch

if TYPE_CHECKING:
    from mcp_use.server import MCPServer


def register_search_tools(server: "MCPServer") -> None:
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

        async with ObsidianClient() as client:
            try:
                results = await client.search_simple(query, context_length)

                # Format results consistently
                matches = []
                for result in results:
                    # Handle different response formats from the API
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
            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

    @server.tool()
    async def search_advanced(dql_query: str) -> str:
        """
        Execute a Dataview DQL query against the vault.

        Requires the Dataview plugin to be installed in Obsidian.
        DQL (Dataview Query Language) allows powerful filtering and
        aggregation of notes based on metadata.

        Args:
            dql_query: Dataview Query Language query string

        Returns:
            JSON array of matching results

        Examples:
            - "TABLE file.ctime FROM #project WHERE status = 'active'"
            - "LIST FROM #research SORT file.mtime DESC"
            - "TASK FROM \"Daily\" WHERE !completed"
        """
        if not dql_query or not dql_query.strip():
            return json.dumps({
                "error": True,
                "type": "ValidationError",
                "message": "DQL query cannot be empty",
            })

        async with ObsidianClient() as client:
            try:
                results = await client.search_dql(dql_query)

                return json.dumps({
                    "success": True,
                    "query": dql_query,
                    "results": results,
                    "total_results": len(results) if isinstance(results, list) else 1,
                })
            except ObsidianAPIError as e:
                # Check if it's a Dataview not installed error
                if "dataview" in str(e).lower():
                    return json.dumps({
                        "error": True,
                        "type": "DataviewNotInstalledError",
                        "message": "Dataview plugin is not installed or enabled in Obsidian",
                    })
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

    @server.tool()
    async def search_jsonlogic(query: str) -> str:
        """
        Execute a JsonLogic query against the vault.

        JsonLogic allows complex filtering using logical operators.
        See https://jsonlogic.com/ for query syntax.

        Args:
            query: JsonLogic query as JSON string

        Returns:
            JSON array of matching results

        Examples:
            - '{"and": [{"glob": ["tags", "project"]}, {"==": [{"var": "frontmatter.status"}, "active"]}]}'
            - '{"in": ["research", {"var": "tags"}]}'
        """
        if not query or not query.strip():
            return json.dumps({
                "error": True,
                "type": "ValidationError",
                "message": "JsonLogic query cannot be empty",
            })

        try:
            query_obj = json.loads(query)
        except json.JSONDecodeError as e:
            return json.dumps({
                "error": True,
                "type": "InvalidJSONError",
                "message": f"Invalid JSON in query: {e}",
            })

        async with ObsidianClient() as client:
            try:
                results = await client.search_jsonlogic(query_obj)

                return json.dumps({
                    "success": True,
                    "query": query_obj,
                    "results": results,
                    "total_results": len(results) if isinstance(results, list) else 1,
                })
            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })
