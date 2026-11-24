"""Result models returned by `Vault` and reused as tool return types.

Timestamps are timezone-aware UTC `datetime`s (serialized as ISO 8601). Paths are
vault-relative with forward slashes. Frontmatter is a JSON-safe dict taken from
Obsidian's metadata cache, so values are typed the way Obsidian types them.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """One file in the vault (any extension)."""

    path: str = Field(description="Vault-relative path, e.g. 'Projects/Plan.md'.")
    extension: str = Field(description="Extension without the dot, e.g. 'md'.")
    size: int = Field(description="Size in bytes.")
    modified: datetime = Field(description="Last modified time (UTC).")


class Link(BaseModel):
    """An outgoing link, embed, or frontmatter link of a note."""

    target: str | None = Field(
        description="Vault path the link resolves to, or null when it does not resolve."
    )
    link: str = Field(description="Raw link text as written, e.g. 'Note#Heading'.")
    display: str | None = Field(default=None, description="Alias or display text, if any.")
    kind: Literal["link", "embed", "frontmatter"] = Field(
        description="'link' for [[wikilinks]]/markdown links, 'embed' for ![[embeds]], "
        "'frontmatter' for links inside properties."
    )


class Note(BaseModel):
    """A note (or other text file) with its Obsidian-parsed metadata."""

    path: str
    content: str = Field(description="Exact file text, including frontmatter, BOM and CRLFs.")
    frontmatter: dict[str, Any] = Field(
        default_factory=dict, description="Parsed properties, as Obsidian reads them."
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Every tag (frontmatter and inline), without '#', deduplicated "
        "case-insensitively like Obsidian.",
    )
    links: list[Link] = Field(default_factory=list, description="Outgoing links.")
    headings: list[str] = Field(default_factory=list, description="Heading texts in order.")
    modified: datetime
    size: int = Field(description="Size in bytes.")


class TagChange(BaseModel):
    """What `Vault.update_tags` did to a note's frontmatter tags."""

    tags: list[str] = Field(description="Frontmatter tags after the call, without '#'.")
    added: list[str] = Field(description="Tags actually added; empty when all were present.")
    removed: list[str] = Field(description="Tags actually removed; empty when none were present.")


class SearchMatch(BaseModel):
    """One matching line."""

    line: int = Field(description="1-based line number.")
    text: str = Field(
        description="The matching line; a line over ~300 characters is cut around the match, "
        "with '…' marking the cut."
    )


class SearchHit(BaseModel):
    """A file with its matching lines."""

    path: str
    matches: list[SearchMatch]


class SearchResults(BaseModel):
    """Search hits, capped at the requested limit."""

    hits: list[SearchHit]
    truncated: bool = Field(description="True when more files matched than the limit allowed.")


class NoteSnapshot(BaseModel):
    """One markdown note inside a `VaultSnapshot` (no content)."""

    path: str
    size: int
    modified: datetime
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)


class VaultSnapshot(BaseModel):
    """The whole vault's structure and metadata, gathered by one eval."""

    notes: list[NoteSnapshot] = Field(description="Every markdown note, sorted by path.")
    folders: list[str] = Field(description="Every folder path (root excluded), sorted.")
