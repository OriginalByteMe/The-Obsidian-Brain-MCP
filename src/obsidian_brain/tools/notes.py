"""Note, link, tag and search tools."""

import asyncio
import re
import unicodedata
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import AfterValidator, BaseModel, Field

from ..exceptions import InvalidArgumentError
from ..models import FileInfo, Note, SearchMatch, TagChange
from ..vault import Vault, get_vault

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
ADDITIVE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
IDEMPOTENT = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

# Obsidian stores names in NFC, so the path a tool echoes back is the NFC one get_note accepts.
NotePath = Annotated[
    str,
    Field(
        min_length=1,
        description="Vault-relative path with forward slashes, e.g. 'Projects/Plan.md'.",
    ),
    AfterValidator(lambda path: unicodedata.normalize("NFC", path)),
]
Tag = Annotated[
    str,
    Field(
        pattern=r"^#?[\w/-]+$",
        description="Tag with or without the leading '#', e.g. 'project/alpha'. "
        "Letters, digits, '_', '-' and '/' only.",
    ),
]

_MAX_GRAPH_NODES = 200
_GRAPH_CONCURRENCY = 8
_MAX_MATCHES_PER_NOTE = 10
# Characters that would end or reshape a wikilink; none may appear in link text.
_UNSAFE_LINK = re.compile(r"[\[\]|#^\x00-\x1f]")


class FileListing(BaseModel):
    files: list[FileInfo]
    total: int = Field(description="Files matching the filter, before paging.")
    next_offset: int | None = Field(
        description="Pass as `offset` to get the next page; null on the last page."
    )


class WriteResult(BaseModel):
    path: str = Field(
        description="Final vault path ('.md' is added unless the path ends in a file type "
        "Obsidian opens)."
    )


class AppendResult(BaseModel):
    path: str
    heading: str | None = Field(
        description="Section the text went to; null when appended at the end of the file."
    )


class DeleteResult(BaseModel):
    path: str
    permanent: bool = Field(description="False: moved to the trash (recoverable). True: gone.")


class TagCount(BaseModel):
    tag: str = Field(description="Tag without '#'.")
    occurrences: int = Field(
        description="How often the tag occurs in the vault, as Obsidian counts it: a note using "
        "it twice counts twice, and 'a/b' also counts toward 'a'. Not a number of notes."
    )


class TagList(BaseModel):
    tags: list[TagCount] = Field(description="Most occurrences first.")
    total: int = Field(description="Distinct tags in the vault, before the limit.")
    truncated: bool = Field(description="True when more tags exist than `limit` returned.")


class TaggedNotes(BaseModel):
    tag: str = Field(description="The tag searched, without '#'.")
    notes: list[str] = Field(description="Vault paths of the notes carrying the tag.")


class TagUpdate(TagChange):
    path: str


class GraphNode(BaseModel):
    path: str
    depth: int = Field(description="Link hops from the start note (0 is the start note).")


class GraphEdge(BaseModel):
    source: str = Field(description="Note containing the link.")
    target: str = Field(description="Note the link points to.")


class LinkGraph(BaseModel):
    center: str
    nodes: list[GraphNode]
    edges: list[GraphEdge] = Field(
        description="Each link once, found while expanding every note up to depth-1 hops out; "
        "links back to already-listed notes are kept, links among the outermost notes are not."
    )
    truncated: bool = Field(description="True when the node cap stopped the traversal early.")


class LinkAdded(BaseModel):
    path: str
    target: str = Field(description="Vault path the link resolves to.")
    link: str = Field(description="The wikilink, e.g. '[[Fiction MOC]]'.")
    added: bool = Field(description="False when the note already linked to the target.")


class NoteMatches(BaseModel):
    path: str
    match_count: int = Field(description="Matching lines in the note (0 for name/tag matches).")
    matches: list[SearchMatch] = Field(
        description=f"First {_MAX_MATCHES_PER_NOTE} matching lines with 1-based line numbers."
    )


class SearchResponse(BaseModel):
    query: str
    hits: list[NoteMatches]
    truncated: bool = Field(description="True when more notes matched than `limit` returned.")


async def link_graph(
    vault: Vault, path: str, direction: Literal["outgoing", "incoming", "both"], depth: int
) -> LinkGraph:
    """Breadth-first link traversal; one eval per expanded note, a level at a time."""
    # lean: one eval per expanded note (8 at a time), backlinks from Obsidian's resolved-link index:
    # depth 3 over 113 notes of a 341-note vault takes ~0.5 s. A single-eval traversal is the
    # upgrade if a vault of many thousand notes makes depth 3 slow.
    gate = asyncio.Semaphore(_GRAPH_CONCURRENCY)

    async def edges_of(note: str) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        async with gate:
            if direction != "incoming":
                found += [
                    (note, link.target) for link in await vault.outgoing_links(note) if link.target
                ]
            if direction != "outgoing":
                found += [(source, note) for source in await vault.backlinks(note)]
        return found

    depths = {path: 0}
    edges: dict[tuple[str, str], None] = {}
    frontier = [path]
    truncated = False
    for level in range(1, depth + 1):
        current, frontier = frontier, []
        for note, found in zip(current, await asyncio.gather(*map(edges_of, current)), strict=True):
            for source, target in found:
                other = target if source == note else source
                if other not in depths:
                    if len(depths) >= _MAX_GRAPH_NODES:
                        truncated = True
                        continue
                    depths[other] = level
                    if other.lower().endswith(".md"):
                        frontier.append(other)
                edges[(source, target)] = None
    return LinkGraph(
        center=path,
        nodes=[GraphNode(path=p, depth=d) for p, d in depths.items()],
        edges=[GraphEdge(source=s, target=t) for s, t in edges],
        truncated=truncated,
    )


async def link_note(vault: Vault, path: str, target: str, heading: str | None) -> LinkAdded:
    """Append `- [[shortest link text]]` to `path` unless it already links to `target`."""
    if _UNSAFE_LINK.search(target):
        raise InvalidArgumentError(
            "`target` must be a plain note name or path: no [[ ]], '|', '#', '^' or line breaks."
        )
    resolved = await vault.resolve_link(target.strip(), path)
    text = await vault.link_text(resolved, path)
    if _UNSAFE_LINK.search(text):
        raise InvalidArgumentError(f"'{resolved}' has characters that cannot be written in a link.")
    link = f"[[{text}]]"
    # The "already linked" check and the write are one atomic edit: concurrent calls add one line.
    added = await vault.append_unless_linked(path, resolved, f"- {link}", heading)
    return LinkAdded(path=path, target=resolved, link=link, added=added)


def register(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY)
    async def list_vault_files(
        folder: Annotated[
            str,
            Field(
                description="Folder to list recursively, e.g. 'Projects' (trailing '/' is fine). "
                "Empty means the whole vault."
            ),
        ] = "",
        extension: Annotated[
            str | None,
            Field(
                pattern=r"^\.?[A-Za-z0-9]+$",
                description="Only files with this extension, e.g. 'md' or 'png'. Omit for all.",
            ),
        ] = None,
        limit: Annotated[
            int, Field(ge=1, le=1000, description="Maximum files to return in this page.")
        ] = 200,
        offset: Annotated[
            int, Field(ge=0, description="Files to skip, for paging (see `next_offset`).")
        ] = 0,
    ) -> FileListing:
        """List the files under a vault folder, sorted by path, one page at a time.

        Use search_content to find notes by what they say, get_notes_by_tag to find them by tag.
        Example: list_vault_files(folder="Projects", extension="md", limit=50)
        """
        files = await get_vault().list_files(folder, extension)
        end = offset + limit
        return FileListing(
            files=files[offset:end], total=len(files), next_offset=end if end < len(files) else None
        )

    @server.tool(annotations=READ_ONLY)
    async def get_note(path: NotePath) -> Note:
        """Read one note: exact text, frontmatter, tags, outgoing links and headings.

        Use list_vault_files to discover paths, search_content to find a note by its text,
        get_links to see what links to it.
        Example: get_note(path="Projects/Plan.md")
        """
        return await get_vault().read_note(path)

    @server.tool(annotations=DESTRUCTIVE)
    async def write_note(
        path: NotePath,
        content: Annotated[
            str,
            Field(
                description="Exact file text, frontmatter included if wanted. Written verbatim: "
                "nothing is added, and backslashes or LaTeX stay as typed."
            ),
        ],
        overwrite: Annotated[
            bool,
            Field(description="False (default): fail if the note exists. True: replace its text."),
        ] = False,
    ) -> WriteResult:
        """Create a note (folders are created as needed), or replace one when overwrite is true.

        Use append_to_note to add to an existing note without replacing it, update_tags to
        change tags only. '.md' is added unless the path ends in a file type Obsidian opens
        (md, canvas, png, pdf, ...), so "Learning Node.js" becomes a note.
        Example: write_note(path="Ideas/Garden.md", content="# Garden\\n\\nPlant beans.")
        """
        return WriteResult(path=await get_vault().write_note(path, content, overwrite))

    @server.tool(annotations=ADDITIVE)
    async def append_to_note(
        path: NotePath,
        content: Annotated[str, Field(min_length=1, description="Text to add, verbatim.")],
        heading: Annotated[
            str | None,
            Field(
                min_length=1,
                description="Existing heading, e.g. 'Log' or '## Log'. The text goes at the end "
                "of that section; the call fails if the heading is missing. "
                "Omit to append at the end of the file.",
            ),
        ] = None,
    ) -> AppendResult:
        """Append text to an existing note, atomically, at the end or under a heading.

        Use write_note to create a note or replace one, add_link to add a link, and
        append_to_daily for a daily note.
        Example: append_to_note(path="Projects/Plan.md", content="- ship it", heading="Tasks")
        """
        await get_vault().append(path, content, heading)
        return AppendResult(path=path, heading=heading)

    @server.tool(annotations=DESTRUCTIVE)
    async def delete_note(
        path: NotePath,
        permanent: Annotated[
            bool,
            Field(description="False (default): move to the trash. True: delete for good."),
        ] = False,
    ) -> DeleteResult:
        """Delete a note or file, to the trash unless permanent is true.

        Use write_note with overwrite to replace content instead of deleting it.
        Example: delete_note(path="Scratch/Old.md")
        """
        await get_vault().delete(path, permanent)
        return DeleteResult(path=path, permanent=permanent)

    @server.tool(annotations=IDEMPOTENT)
    async def update_tags(
        path: NotePath,
        add: Annotated[
            list[Tag] | None,
            Field(
                description="Tags to add to the frontmatter 'tags' property; already-present "
                "tags (any case) are skipped."
            ),
        ] = None,
        remove: Annotated[
            list[Tag] | None,
            Field(description="Tags to remove from the frontmatter 'tags' property (any case)."),
        ] = None,
    ) -> TagUpdate:
        """Add or remove frontmatter tags on a note; the file is left untouched when nothing changes.

        Inline #tags in the body are not edited. When the tags change, the `tags` property is
        rewritten as a block list and every other line of the note stays as it was. Use
        get_notes_by_tag to find notes by tag, write_note to rewrite a whole note.
        Example: update_tags(path="Projects/Plan.md", add=["to-read"], remove=["draft"])
        """
        change = await get_vault().update_tags(path, add or [], remove or [])
        return TagUpdate(path=path, **change.model_dump())

    @server.tool(annotations=READ_ONLY)
    async def list_all_tags(
        limit: Annotated[
            int, Field(ge=1, le=1000, description="Maximum tags to return, most occurrences first.")
        ] = 200,
    ) -> TagList:
        """List every tag in the vault (frontmatter and inline) with how often each occurs.

        Counts are occurrences as Obsidian counts them (a note using a tag twice counts twice),
        not numbers of notes. Use get_notes_by_tag to see which notes carry one tag.
        Example: list_all_tags(limit=50)
        """
        ranked = sorted((await get_vault().tags()).items(), key=lambda kv: (-kv[1], kv[0]))
        return TagList(
            tags=[TagCount(tag=tag, occurrences=count) for tag, count in ranked[:limit]],
            total=len(ranked),
            truncated=len(ranked) > limit,
        )

    @server.tool(annotations=READ_ONLY)
    async def get_notes_by_tag(
        tag: Tag,
        include_nested: Annotated[
            bool,
            Field(description="True (default): 'project' also matches 'project/alpha'."),
        ] = True,
    ) -> TaggedNotes:
        """List the notes carrying a tag, from frontmatter or inline #tags, case-insensitively.

        Use list_all_tags to discover tags, search_content for text, update_tags to change them.
        Example: get_notes_by_tag(tag="project", include_nested=true)
        """
        name = tag.removeprefix("#")
        notes = await get_vault().notes_with_tag(name, include_nested)
        return TaggedNotes(tag=name, notes=sorted(notes))

    @server.tool(annotations=READ_ONLY)
    async def get_links(
        path: NotePath,
        direction: Annotated[
            Literal["outgoing", "incoming", "both"],
            Field(
                description="'outgoing': notes this one links to. 'incoming': notes linking to it "
                "(backlinks). 'both' (default): either."
            ),
        ] = "both",
        depth: Annotated[
            int, Field(ge=1, le=3, description="Link hops to follow from the note (1-3).")
        ] = 1,
    ) -> LinkGraph:
        """Map the notes connected to a note by links, embeds and links in properties.

        Use get_note for one note's own link list, search_content to find notes by text,
        add_link to create a link.
        Example: get_links(path="Projects/Plan.md", direction="incoming", depth=2)
        """
        return await link_graph(get_vault(), path, direction, depth)

    @server.tool(annotations=IDEMPOTENT)
    async def add_link(
        path: NotePath,
        target: Annotated[
            str,
            Field(
                min_length=1,
                description="Note to link to, as a wikilink name ('Fiction MOC') or a path "
                "('Books/Fiction MOC.md'), resolved the way Obsidian resolves [[links]]. "
                "Plain name only: no [[ ]], '|', '#', '^'.",
            ),
        ],
        heading: Annotated[
            str | None,
            Field(
                min_length=1,
                description="Existing heading, e.g. 'See Also', to list the link under. "
                "Omit to append at the end of the note.",
            ),
        ] = None,
    ) -> LinkAdded:
        """Add a '- [[link]]' bullet to a note, written with the shortest unambiguous link text.

        Does nothing (added=false) if the note already links to the target anywhere.
        Use append_to_note for free text, get_links to inspect existing links.
        Example: add_link(path="Reading List.md", target="Fiction MOC", heading="See Also")
        """
        return await link_note(get_vault(), path, target, heading)

    @server.tool(annotations=READ_ONLY)
    async def search_content(
        query: Annotated[
            str,
            Field(
                min_length=1, description="Obsidian search query; syntax in the tool description."
            ),
        ],
        folder: Annotated[
            str | None,
            Field(
                description="Only search under this folder, e.g. 'Projects'. Omit for the vault."
            ),
        ] = None,
        limit: Annotated[int, Field(ge=1, le=100, description="Maximum notes to return.")] = 20,
    ) -> SearchResponse:
        """Search note text and file names with Obsidian's own search engine.

        Use get_notes_by_tag when you know the tag, list_vault_files to browse a folder,
        get_links to follow connections.
        Syntax (case-insensitive): several words match notes containing ALL of them, in any
        order and place ("atlas roadmap"); double quotes match an exact phrase ("atlas roadmap");
        path:Projects/ limits to a folder, tag:#work to a tag, file:name to file names;
        -word excludes, a OR b alternates, /regex/ matches a pattern. A word followed by a colon
        reads as an operator, so quote plain text like "note: value". Notes matched by name or tag
        alone have match_count 0. Returns at most `limit` notes (truncated=true if more match)
        and the first 10 matching lines of each, with line numbers; a line over ~300 characters
        is cut around the match and marked with '…'.
        Example: search_content(query='"quarterly report" path:Work/', limit=10)
        """
        results = await get_vault().search(query, folder, limit)
        return SearchResponse(
            query=query,
            hits=[
                NoteMatches(
                    path=hit.path,
                    match_count=len(hit.matches),
                    matches=hit.matches[:_MAX_MATCHES_PER_NOTE],
                )
                for hit in results.hits
            ],
            truncated=results.truncated,
        )
