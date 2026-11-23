"""Resources: read-only views of the vault for clients that browse rather than call tools.

Each read asks Obsidian directly; nothing is cached, so a resource is as current as the vault.
Failures raise `ResourceNotFoundError` / `ResourceError` (protocol errors), never a body that
merely looks like data.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import quote

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError
from pydantic import BaseModel

from .exceptions import NoteNotFoundError, ObsidianError
from .knowledge import KNOWLEDGE_BASE_PATH, compute_stats
from .models import FileInfo
from .vault import get_vault


class _FileEntry(FileInfo):
    uri: str | None = None


class _FileList(BaseModel):
    total: int
    files: list[_FileEntry]


@contextmanager
def _resource_errors() -> Iterator[None]:
    """Turn a domain error into the matching resource error, message kept."""
    try:
        yield
    except NoteNotFoundError as error:
        raise ResourceNotFoundError(str(error)) from error
    except ObsidianError as error:
        raise ResourceError(str(error)) from error


def register(server: MCPServer) -> None:
    @server.resource("vault://files", mime_type="application/json")
    async def vault_files() -> str:
        """Every file in the vault as JSON: path, extension, size, modified time (UTC).

        Markdown notes also carry the `vault://note/...` URI that reads them. Use the
        list_vault_files tool instead to page through a large vault or list one folder.
        """
        with _resource_errors():
            files = await get_vault().list_files()
        entries = [
            _FileEntry(
                **f.model_dump(),
                uri=f"vault://note/{quote(f.path, safe='/')}" if f.extension == "md" else None,
            )
            for f in sorted(files, key=lambda f: f.path)
        ]
        return _FileList(total=len(entries), files=entries).model_dump_json(exclude_none=True)

    @server.resource("vault://note/{+path}", mime_type="text/markdown")
    async def vault_note(path: str) -> str:
        """The exact text of one note (frontmatter included); `/` in the path may be unencoded."""
        with _resource_errors():
            return (await get_vault().read_note(path)).content

    @server.resource("vault://tags", mime_type="application/json")
    async def vault_tags() -> str:
        """Every tag in the vault (frontmatter and inline) with its note count, as JSON."""
        with _resource_errors():
            tags = await get_vault().tags()
        ordered = dict(sorted(tags.items(), key=lambda item: (-item[1], item[0])))
        return json.dumps(ordered, ensure_ascii=False)

    @server.resource("vault://stats", mime_type="application/json")
    async def vault_stats() -> str:
        """Note, folder, tag, link and orphan counts as JSON; `Obsidian Brain/` is not counted."""
        with _resource_errors():
            snapshot = await get_vault().snapshot()
        return compute_stats(snapshot).model_dump_json()

    @server.resource("vault://knowledge", mime_type="text/markdown")
    async def vault_knowledge() -> str:
        """The generated vault overview (folders, tags, hubs, links, orphans) as markdown."""
        try:
            with _resource_errors():
                return (await get_vault().read_note(KNOWLEDGE_BASE_PATH)).content
        except ResourceNotFoundError as error:
            raise ResourceNotFoundError(
                "The knowledge base has not been generated yet. Call the build_knowledge_base tool."
            ) from error
