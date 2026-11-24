"""Memory tools: notes the model keeps for itself across sessions, in `Obsidian Brain/memories/`."""

from datetime import datetime
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from ..exceptions import InvalidArgumentError, NoteExistsError, NoteNotFoundError
from ..memory import (
    MEMORIES_PATH,
    display_name,
    memory_name_of,
    memory_text,
    slugify,
    split_frontmatter,
    utc_now,
)
from ..models import NoteSnapshot
from ..vault import Vault, get_vault
from .notes import DESTRUCTIVE, READ_ONLY

MemoryName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        description="Memory name, e.g. 'vault-overview' or 'Project Alpha decisions'. Names are "
        "matched by slug: lowercased, every run of characters other than letters and digits "
        "becomes one '-'. 'Project X' and 'project_x' are the same memory; 'A/B' and 'AB' are not.",
    ),
]


class MemoryInfo(BaseModel):
    name: str = Field(description="The memory's name, as stored in its `name` property.")
    path: str = Field(description="Vault path of the memory file.")
    type: str | None = Field(description="Memory type from frontmatter, if set.")
    created: str | None = Field(description="`created` frontmatter value, if set.")
    updated: str | None = Field(description="`updated` frontmatter value, if set.")
    modified: datetime = Field(description="File modification time (UTC).")


class MemoryList(BaseModel):
    folder: str = Field(description="Folder the memories live in.")
    memories: list[MemoryInfo] = Field(description="Sorted by path.")


class MemoryContent(MemoryInfo):
    content: str = Field(description="Memory body, without the frontmatter block.")
    tags: list[str] = Field(description="Every tag in the memory, without '#'.")
    frontmatter: dict[str, Any] = Field(description="All frontmatter properties.")


class MemoryWritten(BaseModel):
    name: str
    path: str
    action: Literal["created", "updated"]


class MemoryDeleted(BaseModel):
    name: str
    path: str = Field(description="Where the file was; it is in Obsidian's trash now.")


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def _name(note: NoteSnapshot) -> str:
    """A memory's name: its `name` property, else its file name inside the memories folder."""
    stored = note.frontmatter.get("name")
    return display_name(str(stored)) if stored else memory_name_of(note.path)


def _info(note: NoteSnapshot) -> MemoryInfo:
    fm = note.frontmatter
    return MemoryInfo(
        name=_name(note),
        path=note.path,
        type=_text(fm.get("type")),
        created=_text(fm.get("created")),
        updated=_text(fm.get("updated")),
        modified=note.modified,
    )


async def _find(vault: Vault, name: str) -> NoteSnapshot | None:
    """The one memory whose name has this slug; None if there is none, an error if several."""
    slug = slugify(name)
    matches = [
        n for n in (await vault.snapshot(MEMORIES_PATH)).notes if _slug_or_none(_name(n)) == slug
    ]
    if len(matches) > 1:
        paths = ", ".join(n.path for n in matches)
        raise InvalidArgumentError(
            f"Memory name {name!r} is ambiguous: {paths} all reduce to '{slug}'. "
            "Rename or delete all but one in Obsidian."
        )
    return matches[0] if matches else None


def _slug_or_none(name: str) -> str | None:
    try:
        return slugify(name)
    except InvalidArgumentError:
        return None


def _missing(name: str) -> NoteNotFoundError:
    return NoteNotFoundError(f"No memory named {name!r}. Use list_memories to see the names.")


def register(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY)
    async def list_memories() -> MemoryList:
        """List every memory with its type and timestamps, without reading their bodies.

        Use read_memory to open one, write_memory to save one, delete_memory to drop one.
        Start a session by listing, then read only the memories relevant to the task.
        Example: list_memories()
        """
        notes = (await get_vault().snapshot(MEMORIES_PATH)).notes
        return MemoryList(folder=MEMORIES_PATH, memories=[_info(n) for n in notes])

    @server.tool(annotations=READ_ONLY)
    async def read_memory(name: MemoryName) -> MemoryContent:
        """Read one memory: body, type, timestamps, tags and all frontmatter.

        Use list_memories to see which names exist, write_memory to change one.
        Example: read_memory(name="vault-overview")
        """
        vault = get_vault()
        found = await _find(vault, name)
        if found is None:
            raise _missing(name)
        note = await vault.read_note(found.path)
        return MemoryContent(
            **_info(found).model_dump(),
            content=split_frontmatter(note.content)[1],
            tags=note.tags,
            frontmatter=note.frontmatter,
        )

    @server.tool(annotations=DESTRUCTIVE)
    async def write_memory(
        name: MemoryName,
        content: Annotated[
            str,
            Field(
                description="Markdown body of the memory, written verbatim. Replaces the old body; "
                "frontmatter properties (tags, custom ones, created) are kept."
            ),
        ],
        memory_type: Annotated[
            str | None,
            Field(
                max_length=50,
                description="Free-form kind, e.g. 'project', 'preference', 'learning'. "
                "Omit to keep the current type (or none for a new memory).",
            ),
        ] = None,
    ) -> MemoryWritten:
        """Create a memory, or replace the body of the one with this name.

        Use it for project context, user preferences, conventions and learnings worth keeping
        across sessions. A new memory is saved as `Obsidian Brain/memories/<slug>.md`. Updating
        keeps `created` and every other property and sets `updated`. Fails, instead of
        overwriting, when a memory under a different spelling already has the same slug: write
        to the name list_memories shows. Use read_memory first to extend rather than replace.
        Example: write_memory(name="Project Alpha", content="Deadline is May 3.", memory_type="project")
        """
        vault = get_vault()
        shown = display_name(name)
        found = await _find(vault, name)
        now = utc_now()
        if found is None:
            frontmatter: dict[str, object] = {"name": shown}
            if memory_type:
                frontmatter["type"] = memory_type
            frontmatter |= {"created": now, "updated": now}
            path = await vault.write_note(
                f"{MEMORIES_PATH}/{slugify(name)}.md", memory_text(frontmatter, content)
            )
            return MemoryWritten(name=shown, path=path, action="created")

        if _name(found) != shown:
            raise NoteExistsError(
                f"Memory {_name(found)!r} already uses the slug '{slugify(name)}'. "
                f"Write to {_name(found)!r} to update it, or pick a different name."
            )
        # One atomic edit inside Obsidian: the body is replaced and only `type`, `updated` and, where
        # missing, `name` and `created` are written; every other frontmatter line stays as it is.
        properties: dict[str, object] = {"updated": now}
        if memory_type:
            properties["type"] = memory_type
        modified = found.modified.strftime("%Y-%m-%dT%H:%M:%SZ")
        await vault.replace_body(
            found.path,
            content,
            properties=properties,
            defaults={"name": shown, "created": modified},
        )
        return MemoryWritten(name=shown, path=found.path, action="updated")

    @server.tool(annotations=DESTRUCTIVE)
    async def delete_memory(name: MemoryName) -> MemoryDeleted:
        """Delete a memory that is outdated or wrong; the file goes to Obsidian's trash.

        Use list_memories to check the name, write_memory to correct a memory instead.
        Example: delete_memory(name="old-project-notes")
        """
        vault = get_vault()
        found = await _find(vault, name)
        if found is None:
            raise _missing(name)
        await vault.delete(found.path)
        return MemoryDeleted(name=_name(found), path=found.path)
