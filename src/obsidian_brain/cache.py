"""
In-memory cache for vault structure with on-demand refresh.

Provides efficient access to vault metadata without repeated CLI calls.
The cache must be explicitly refreshed via the refresh_vault_structure tool.
"""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from .models import (
    FolderNode,
    NoteMetadata,
    VaultStats,
    VaultStructure,
)
from .utils.wikilinks import extract_wikilinks

if TYPE_CHECKING:
    from .protocol import VaultClient


class CacheNotInitializedError(Exception):
    """Raised when cache is accessed before initialization."""

    def __init__(self):
        super().__init__(
            "Vault structure cache not initialized. "
            "Call refresh_vault_structure tool first."
        )


class VaultCache:
    """
    In-memory cache for vault structure with on-demand refresh.

    The cache stores:
    - Folder hierarchy
    - Note metadata (tags, links, frontmatter)
    - Backlink index (computed from outgoing links)
    - Aggregate statistics

    Usage:
        cache = VaultCache()
        await cache.refresh(client)
        structure = cache.get_structure()
    """

    def __init__(self):
        self._structure: VaultStructure | None = None
        self._lock = asyncio.Lock()
        self._backlink_index: dict[str, list[str]] = {}

    @property
    def is_initialized(self) -> bool:
        """Check if cache has been initialized."""
        return self._structure is not None

    def get_structure(self) -> VaultStructure:
        """
        Get cached structure, raises if not initialized.

        Returns:
            The cached VaultStructure

        Raises:
            CacheNotInitializedError: If refresh hasn't been called
        """
        if self._structure is None:
            raise CacheNotInitializedError()
        return self._structure

    def get_backlinks(self, path: str) -> list[str]:
        """
        Get notes that link to the specified path.

        Args:
            path: Note path to find backlinks for

        Returns:
            List of paths that link to this note
        """
        if not self.is_initialized:
            raise CacheNotInitializedError()
        return self._backlink_index.get(path, [])

    def get_note_metadata(self, path: str) -> NoteMetadata | None:
        """
        Get cached metadata for a specific note.

        Args:
            path: Note path

        Returns:
            NoteMetadata if found, None otherwise
        """
        if not self.is_initialized:
            raise CacheNotInitializedError()

        for note in self._structure.notes:
            if note.path == path:
                return note
        return None

    def get_all_tags(self) -> dict[str, int]:
        """
        Get all tags with their usage counts.

        Returns:
            Dict mapping tag name to count
        """
        if not self.is_initialized:
            raise CacheNotInitializedError()

        tag_counts: dict[str, int] = {}
        for note in self._structure.notes:
            for tag in note.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return tag_counts

    def invalidate_path(self, path: str) -> None:
        """
        Invalidate cached data for a specific note path.

        Removes the note from the cached structure so stale data isn't served.
        A full refresh() is needed to get updated data for this path.

        Args:
            path: Note path to invalidate
        """
        if self._structure is None:
            return

        # Remove note from cached notes list
        self._structure.notes = [
            n for n in self._structure.notes if n.path != path
        ]

        # Remove from backlink index
        self._backlink_index.pop(path, None)

        # Remove references to this path in other backlink entries
        for target, sources in self._backlink_index.items():
            if path in sources:
                sources.remove(path)

    def get_notes_by_tag(self, tag: str) -> list[str]:
        """
        Get all note paths that have a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of note paths with this tag
        """
        if not self.is_initialized:
            raise CacheNotInitializedError()

        return [note.path for note in self._structure.notes if tag in note.tags]

    async def refresh(self, client: "VaultClient") -> VaultStructure:
        """
        Rebuild structure from vault.

        This is a potentially slow operation for large vaults as it:
        1. Bulk-lists all files via CLI (single call)
        2. Fetches metadata for each note with bounded concurrency
        3. Extracts wikilinks from content
        4. Builds backlink index
        5. Computes statistics

        Args:
            client: VaultClient instance to use for vault operations

        Returns:
            The refreshed VaultStructure
        """
        async with self._lock:
            self._structure = await self._build_structure(client)
            return self._structure

    async def _build_structure(self, client: "VaultClient") -> VaultStructure:
        """Internal method to build complete structure."""
        # Step 1: Get all files via bulk listing (single CLI call)
        file_paths = await client.get_all_files("/")

        # Step 2: Build folder hierarchy from file paths
        folders = self._build_folder_hierarchy(file_paths)

        # Step 3: Fetch metadata for all markdown files with bounded concurrency
        md_files = [f for f in file_paths if f.endswith(".md")]
        notes = await self._fetch_notes_concurrent(client, md_files)

        # Step 4: Build backlink index
        self._backlink_index = self._build_backlink_index(notes, md_files)

        # Step 5: Populate incoming_links from backlink index
        for note in notes:
            note.incoming_links = self._backlink_index.get(note.path, [])

        # Step 6: Compute statistics
        all_tags = set()
        total_links = 0
        orphan_count = 0

        for note in notes:
            all_tags.update(note.tags)
            total_links += len(note.outgoing_links)
            if not note.incoming_links and not note.outgoing_links:
                orphan_count += 1

        stats = VaultStats(
            total_notes=len(notes),
            total_folders=len(folders),
            total_tags=len(all_tags),
            total_links=total_links,
            orphan_notes=orphan_count,
        )

        return VaultStructure(
            folders=folders,
            notes=notes,
            stats=stats,
            refreshed_at=datetime.now(),
        )

    async def _fetch_notes_concurrent(
        self, client: "VaultClient", md_files: list[str]
    ) -> list[NoteMetadata]:
        """Fetch note metadata with semaphore-bounded concurrency."""
        semaphore = asyncio.Semaphore(10)
        notes: list[NoteMetadata] = []

        async def fetch_one(file_path: str) -> NoteMetadata | None:
            async with semaphore:
                try:
                    note_data = await client.get_note(file_path, include_metadata=True)
                    content = note_data.get("content", "")
                    outgoing_links = extract_wikilinks(content)
                    title = self._extract_title(file_path, content)

                    return NoteMetadata(
                        path=file_path,
                        title=title,
                        tags=note_data.get("tags", []),
                        outgoing_links=outgoing_links,
                        incoming_links=[],
                        frontmatter=note_data.get("frontmatter", {}),
                        modified=note_data.get("modified"),
                    )
                except Exception:
                    return None

        tasks = [fetch_one(fp) for fp in md_files]
        results = await asyncio.gather(*tasks)
        notes = [r for r in results if r is not None]
        return notes

    def _build_folder_hierarchy(self, file_paths: list[str]) -> list[FolderNode]:
        """Build folder tree from flat file path list."""
        # Collect all unique folder paths
        folder_paths: set[str] = set()
        for fp in file_paths:
            parts = fp.split("/")
            # Build all ancestor folder paths
            for i in range(1, len(parts)):
                folder_paths.add("/".join(parts[:i]))

        if not folder_paths:
            return []

        # Build tree from sorted paths
        nodes: dict[str, FolderNode] = {}
        root_folders: list[FolderNode] = []

        for fp in sorted(folder_paths):
            name = fp.split("/")[-1]
            node = FolderNode(name=name, path=fp + "/", children=[])
            nodes[fp] = node

            # Find parent
            parent_path = "/".join(fp.split("/")[:-1])
            if parent_path and parent_path in nodes:
                nodes[parent_path].children.append(node)
            else:
                root_folders.append(node)

        return root_folders

    async def _get_directory_tree(
        self, client: "VaultClient", path: str
    ) -> dict[str, list]:
        """
        Recursively build directory tree and collect files.

        Returns:
            Dict with 'folders' (list of FolderNode) and 'files' (list of paths)
        """
        folders: list[FolderNode] = []
        files: list[str] = []

        try:
            entries = await client.list_directory(path)
        except Exception:
            return {"folders": folders, "files": files}

        for entry in entries:
            name = entry["name"]
            entry_type = entry["type"]

            entry_path = name if path == "/" else f"{path.rstrip('/')}/{name}"

            if entry_type == "folder":
                # Recurse into subfolder
                sub_result = await self._get_directory_tree(client, entry_path)

                folder = FolderNode(
                    name=name,
                    path=entry_path + "/",
                    children=sub_result["folders"],
                )
                folders.append(folder)
                files.extend(sub_result["files"])
            else:
                files.append(entry_path)

        return {"folders": folders, "files": files}

    def _extract_title(self, path: str, content: str) -> str:
        """
        Extract title from note path or content.

        Prefers H1 heading if present, falls back to filename.
        """
        # Try to find H1 heading
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("# ") and not line.startswith("## "):
                return line[2:].strip()

        # Fall back to filename without extension
        filename = path.split("/")[-1]
        if filename.endswith(".md"):
            filename = filename[:-3]
        return filename

    def _build_backlink_index(
        self, notes: list[NoteMetadata], all_paths: list[str]
    ) -> dict[str, list[str]]:
        """
        Build reverse index of backlinks.

        Maps note path -> list of paths that link to it.
        """
        index: dict[str, list[str]] = {}

        # Build a map from note names to paths for resolution
        name_to_path: dict[str, str] = {}
        for path in all_paths:
            # Get filename without extension
            name = path.split("/")[-1]
            if name.endswith(".md"):
                name = name[:-3]
            name_to_path[name.lower()] = path

            # Also map full path without extension
            path_no_ext = path[:-3] if path.endswith(".md") else path
            name_to_path[path_no_ext.lower()] = path

        for note in notes:
            for link in note.outgoing_links:
                # Resolve link to actual path
                resolved = self._resolve_link(link, name_to_path)
                if resolved:
                    if resolved not in index:
                        index[resolved] = []
                    if note.path not in index[resolved]:
                        index[resolved].append(note.path)

        return index

    def _resolve_link(
        self, link: str, name_to_path: dict[str, str]
    ) -> str | None:
        """
        Resolve a wikilink to a full path.

        Handles:
        - Full paths: "folder/note"
        - Simple names: "note"
        """
        # Normalize the link
        link_lower = link.lower()

        # Try exact match first
        if link_lower in name_to_path:
            return name_to_path[link_lower]

        # Try with .md extension
        if f"{link_lower}.md" in name_to_path:
            return name_to_path[f"{link_lower}.md"]

        # Try just the note name (last component)
        name_only = link.split("/")[-1].lower()
        if name_only in name_to_path:
            return name_to_path[name_only]

        return None


# Global singleton instance
vault_cache = VaultCache()
