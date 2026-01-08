"""
Async HTTP client for Obsidian Local REST API.

Wraps the Obsidian Local REST API endpoints with typed methods
and proper error handling.
"""

import os
from typing import Any

import httpx


class ObsidianAPIError(Exception):
    """Raised when Obsidian API returns an error."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Obsidian API error ({status_code}): {message}")


class NoteNotFoundError(ObsidianAPIError):
    """Raised when a note doesn't exist."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(404, f"Note not found: {path}")


class ObsidianClient:
    """
    Async wrapper for Obsidian Local REST API.

    Handles authentication, SSL verification, and response parsing.
    Uses context manager for proper resource management.

    Example:
        async with ObsidianClient() as client:
            notes = await client.list_directory("/")
            content = await client.get_note("Projects/MyNote.md")
    """

    def __init__(
        self,
        api_key: str | None = None,
        host: str | None = None,
        port: int | None = None,
        verify_ssl: bool | None = None,
        url: str | None = None,
    ):
        """
        Initialize the Obsidian client.

        Args:
            api_key: Bearer token for authentication. Defaults to OBSIDIAN_API_KEY env var.
            host: API host. Defaults to OBSIDIAN_HOST env var or "127.0.0.1".
            port: API port. Defaults to OBSIDIAN_PORT env var or 27124.
            verify_ssl: Whether to verify SSL cert. Defaults to OBSIDIAN_VERIFY_SSL env var or False.
            url: Full base URL override (e.g., "http://localhost:27124"). 
                 Defaults to OBSIDIAN_URL env var. If set, overrides host/port.
        """
        self.api_key = api_key or os.getenv("OBSIDIAN_API_KEY", "")
        
        # Check for full URL override first
        base_url_override = url or os.getenv("OBSIDIAN_URL")
        
        if base_url_override:
            # Use full URL, strip trailing slash
            self.base_url = base_url_override.rstrip("/")
            self.host = ""
            self.port = 0
        else:
            # Construct from host/port (original behavior)
            self.host = host or os.getenv("OBSIDIAN_HOST", "127.0.0.1")
            self.port = port or int(os.getenv("OBSIDIAN_PORT", "27124"))
            self.base_url = f"https://{self.host}:{self.port}"

        verify_ssl_env = os.getenv("OBSIDIAN_VERIFY_SSL", "false").lower()
        self.verify_ssl = verify_ssl if verify_ssl is not None else verify_ssl_env == "true"

        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ObsidianClient":
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            verify=self.verify_ssl,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager and close client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not in context."""
        if self._client is None:
            raise RuntimeError(
                "ObsidianClient must be used as async context manager: "
                "async with ObsidianClient() as client: ..."
            )
        return self._client

    def _get_headers(self, accept_json: bool = False) -> dict[str, str]:
        """Build request headers with authentication."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        if accept_json:
            headers["Accept"] = "application/vnd.olrapi.note+json"
        else:
            headers["Accept"] = "text/markdown"
        return headers

    async def _handle_response(
        self, response: httpx.Response, path: str = ""
    ) -> httpx.Response:
        """Handle response and raise appropriate errors."""
        if response.status_code == 404:
            raise NoteNotFoundError(path)
        if response.status_code >= 400:
            try:
                error_detail = response.json().get("message", response.text)
            except Exception:
                error_detail = response.text
            raise ObsidianAPIError(response.status_code, error_detail)
        return response

    # -------------------------------------------------------------------------
    # Directory Operations
    # -------------------------------------------------------------------------

    async def list_directory(self, path: str = "/") -> list[dict[str, Any]]:
        """
        List files and folders at the specified path.

        Args:
            path: Relative path in vault (default: root "/")

        Returns:
            List of dicts with 'name' and 'type' ('file' or 'folder') keys
        """
        # Ensure path ends with / for directory listing
        if not path.endswith("/"):
            path = path + "/"
        url = "/vault/" if path == "/" else f"/vault/{path}"

        response = await self.client.get(url, headers=self._get_headers())
        await self._handle_response(response, path)

        data = response.json()
        # API returns {"files": [...]} with file paths
        files = data.get("files", [])

        result = []
        for f in files:
            name = f if isinstance(f, str) else f.get("path", f.get("name", ""))
            is_folder = name.endswith("/")
            result.append({
                "name": name.rstrip("/"),
                "type": "folder" if is_folder else "file",
            })
        return result

    async def get_all_files(self, path: str = "/") -> list[str]:
        """
        Recursively get all file paths under a directory.

        Args:
            path: Starting path (default: root)

        Returns:
            List of all file paths (relative to vault root)
        """
        all_files = []
        entries = await self.list_directory(path)

        for entry in entries:
            entry_path = entry["name"] if path == "/" else f"{path.rstrip('/')}/{entry['name']}"
            if entry["type"] == "folder":
                # Recurse into folder
                sub_files = await self.get_all_files(entry_path)
                all_files.extend(sub_files)
            else:
                all_files.append(entry_path)

        return all_files

    # -------------------------------------------------------------------------
    # Note Operations
    # -------------------------------------------------------------------------

    async def get_note(
        self, path: str, include_metadata: bool = True
    ) -> dict[str, Any]:
        """
        Get a note's content and optionally its metadata.

        Args:
            path: Path to the note (e.g., "Projects/MyProject.md")
            include_metadata: If True, returns JSON with metadata; else raw markdown

        Returns:
            Dict with 'content' and metadata fields, or just 'content' if not include_metadata
        """
        url = f"/vault/{path}"
        headers = self._get_headers(accept_json=include_metadata)

        response = await self.client.get(url, headers=headers)
        await self._handle_response(response, path)

        if include_metadata:
            data = response.json()
            return {
                "path": path,
                "content": data.get("content", ""),
                "tags": data.get("tags", []),
                "frontmatter": data.get("frontmatter", {}),
                "modified": data.get("modified"),
            }
        else:
            return {"path": path, "content": response.text}

    async def note_exists(self, path: str) -> bool:
        """
        Check if a note exists in the vault.

        Args:
            path: Path to check

        Returns:
            True if note exists, False otherwise
        """
        try:
            await self.get_note(path, include_metadata=False)
            return True
        except NoteNotFoundError:
            return False

    async def create_note(self, path: str, content: str) -> None:
        """
        Create a new note or overwrite existing.

        Args:
            path: Path for the note
            content: Full note content including frontmatter
        """
        url = f"/vault/{path}"
        headers = self._get_headers()
        headers["Content-Type"] = "text/markdown"

        response = await self.client.put(url, content=content, headers=headers)
        await self._handle_response(response, path)

    async def update_note(self, path: str, content: str) -> None:
        """
        Replace a note's entire content.

        Args:
            path: Path to the note
            content: New content (replaces everything)
        """
        # Same as create - PUT replaces content
        await self.create_note(path, content)

    async def append_to_note(self, path: str, content: str) -> None:
        """
        Append content to an existing note.

        Args:
            path: Path to the note
            content: Content to append
        """
        url = f"/vault/{path}"
        headers = self._get_headers()
        headers["Content-Type"] = "text/markdown"

        response = await self.client.post(url, content=content, headers=headers)
        await self._handle_response(response, path)

    async def patch_note(
        self,
        path: str,
        operation: str,
        content: str,
        target_type: str | None = None,
        target: str | None = None,
    ) -> None:
        """
        Partially update a note.

        Args:
            path: Path to the note
            operation: "append", "prepend", or "replace"
            content: Content to insert
            target_type: "heading", "block", or "frontmatter"
            target: Target identifier (heading name, block ID, frontmatter key)
        """
        url = f"/vault/{path}"
        headers = self._get_headers()
        headers["Content-Type"] = "text/markdown"
        headers["Operation"] = operation

        if target_type:
            headers["Target-Type"] = target_type
        if target:
            headers["Target"] = target

        response = await self.client.patch(url, content=content, headers=headers)
        await self._handle_response(response, path)

    async def delete_note(self, path: str) -> None:
        """
        Delete a note from the vault.

        Args:
            path: Path to the note to delete
        """
        url = f"/vault/{path}"
        headers = self._get_headers()

        response = await self.client.delete(url, headers=headers)
        await self._handle_response(response, path)

    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------

    async def search_simple(
        self, query: str, context_length: int = 100
    ) -> list[dict[str, Any]]:
        """
        Perform simple text search across the vault.

        Args:
            query: Search query string
            context_length: Characters of context around matches

        Returns:
            List of matches with file paths, snippets, and scores
        """
        url = "/search/simple/"
        params = {"query": query, "contextLength": context_length}
        headers = self._get_headers()

        response = await self.client.post(url, params=params, headers=headers)
        await self._handle_response(response)

        return response.json()

    async def search_dql(self, query: str) -> list[dict[str, Any]]:
        """
        Execute a Dataview DQL query.

        Args:
            query: Dataview Query Language query string

        Returns:
            Query results
        """
        url = "/search/"
        headers = self._get_headers()
        headers["Content-Type"] = "application/vnd.olrapi.dataview.dql+txt"

        response = await self.client.post(url, content=query, headers=headers)
        await self._handle_response(response)

        return response.json()

    async def search_jsonlogic(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Execute a JsonLogic query.

        Args:
            query: JsonLogic query object

        Returns:
            Query results
        """
        url = "/search/"
        headers = self._get_headers()
        headers["Content-Type"] = "application/vnd.olrapi.jsonlogic+json"

        response = await self.client.post(url, json=query, headers=headers)
        await self._handle_response(response)

        return response.json()

    # -------------------------------------------------------------------------
    # Periodic Notes
    # -------------------------------------------------------------------------

    async def get_periodic(
        self, period: str = "daily", date: str | None = None
    ) -> dict[str, Any]:
        """
        Get a periodic note (daily, weekly, monthly, etc.).

        Args:
            period: Period type - "daily", "weekly", "monthly", "quarterly", "yearly"
            date: Optional specific date (format depends on period)

        Returns:
            Note content and metadata
        """
        if date:
            # Parse date into year/month/day components
            parts = date.split("-")
            if len(parts) >= 3:
                url = f"/periodic/{period}/{parts[0]}/{parts[1]}/{parts[2]}/"
            else:
                url = f"/periodic/{period}/"
        else:
            url = f"/periodic/{period}/"

        headers = self._get_headers(accept_json=True)
        response = await self.client.get(url, headers=headers)
        await self._handle_response(response, f"periodic/{period}")

        data = response.json()
        return {
            "content": data.get("content", ""),
            "tags": data.get("tags", []),
            "frontmatter": data.get("frontmatter", {}),
        }

    async def append_periodic(
        self, content: str, period: str = "daily", date: str | None = None
    ) -> None:
        """
        Append content to a periodic note.

        Args:
            content: Content to append
            period: Period type
            date: Optional specific date
        """
        if date:
            parts = date.split("-")
            if len(parts) >= 3:
                url = f"/periodic/{period}/{parts[0]}/{parts[1]}/{parts[2]}/"
            else:
                url = f"/periodic/{period}/"
        else:
            url = f"/periodic/{period}/"

        headers = self._get_headers()
        headers["Content-Type"] = "text/markdown"

        response = await self.client.post(url, content=content, headers=headers)
        await self._handle_response(response, f"periodic/{period}")

    async def update_periodic(
        self, content: str, period: str = "daily", date: str | None = None
    ) -> None:
        """
        Update/replace a periodic note.

        Args:
            content: New content
            period: Period type
            date: Optional specific date
        """
        if date:
            parts = date.split("-")
            if len(parts) >= 3:
                url = f"/periodic/{period}/{parts[0]}/{parts[1]}/{parts[2]}/"
            else:
                url = f"/periodic/{period}/"
        else:
            url = f"/periodic/{period}/"

        headers = self._get_headers()
        headers["Content-Type"] = "text/markdown"

        response = await self.client.put(url, content=content, headers=headers)
        await self._handle_response(response, f"periodic/{period}")

    # -------------------------------------------------------------------------
    # Server Info
    # -------------------------------------------------------------------------

    async def get_server_info(self) -> dict[str, Any]:
        """
        Get server information and authentication status.

        Returns:
            Server info including version and auth status
        """
        response = await self.client.get("/")
        await self._handle_response(response)
        return response.json()
