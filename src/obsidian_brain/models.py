"""
Pydantic models for Obsidian Brain MCP.

Defines data structures for vault representation, note metadata,
and API responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class FolderNode(BaseModel):
    """Represents a folder in the vault hierarchy."""

    name: str
    path: str  # Relative path from vault root, e.g., "Projects/Active/"
    children: list["FolderNode"] = Field(default_factory=list)


class NoteMetadata(BaseModel):
    """Metadata for a single note in the vault."""

    path: str  # e.g., "Projects/Active/MyProject.md"
    title: str  # Auto-extracted from filename or H1
    tags: list[str] = Field(default_factory=list)  # From frontmatter
    outgoing_links: list[str] = Field(default_factory=list)  # [[wikilinks]] this note contains
    incoming_links: list[str] = Field(default_factory=list)  # Notes that link TO this note
    frontmatter: dict = Field(default_factory=dict)  # Full frontmatter as dict
    modified: datetime | None = None  # Last modified timestamp


class VaultStats(BaseModel):
    """Aggregate statistics about the vault."""

    total_notes: int = 0
    total_folders: int = 0
    total_tags: int = 0
    total_links: int = 0
    orphan_notes: int = 0  # Notes with no incoming or outgoing links


class VaultStructure(BaseModel):
    """Complete vault structure for caching."""

    folders: list[FolderNode] = Field(default_factory=list)
    notes: list[NoteMetadata] = Field(default_factory=list)
    stats: VaultStats = Field(default_factory=VaultStats)
    refreshed_at: datetime = Field(default_factory=datetime.now)


class NoteContent(BaseModel):
    """Full note content with metadata, returned by get_note."""

    path: str
    content: str
    tags: list[str] = Field(default_factory=list)
    outgoing_links: list[str] = Field(default_factory=list)
    frontmatter: dict = Field(default_factory=dict)
    modified: datetime | None = None


class FileEntry(BaseModel):
    """Entry in a directory listing."""

    name: str
    type: str  # "file" or "folder"


class SearchMatch(BaseModel):
    """A single search result match."""

    path: str
    matches: list[str] = Field(default_factory=list)  # Matched text snippets
    score: float = 0.0


class LinkGraphNode(BaseModel):
    """Node in a link graph traversal result."""

    path: str
    depth: int


class LinkGraphEdge(BaseModel):
    """Edge in a link graph traversal result."""

    source: str  # Note path that contains the link
    target: str  # Note path being linked to


class LinkGraph(BaseModel):
    """Subgraph of notes centered on a starting node."""

    center: str
    nodes: list[LinkGraphNode] = Field(default_factory=list)
    edges: list[LinkGraphEdge] = Field(default_factory=list)


# Enable forward reference resolution for recursive types
FolderNode.model_rebuild()
