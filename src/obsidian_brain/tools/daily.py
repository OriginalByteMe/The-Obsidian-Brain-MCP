"""Daily note tools."""

import datetime as dt
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from ..exceptions import InvalidArgumentError
from ..models import Note
from ..vault import get_vault
from .notes import ADDITIVE, READ_ONLY, Tag

Day = Annotated[
    Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")] | None,
    Field(
        description="Day as YYYY-MM-DD, a real calendar date, e.g. '2026-11-22'. Omit for today."
    ),
]
LinkName = Annotated[
    str,
    Field(
        min_length=1,
        pattern=r"^[^\[\]\r\n]+$",
        description="Note name or path to link, without [[ ]].",
    ),
]


class DailyNote(BaseModel):
    date: str = Field(description="The day, YYYY-MM-DD.")
    path: str = Field(description="Where that day's note lives, or would be created.")
    exists: bool = Field(description="False when there is no note for that day; none is created.")
    note: Note | None = Field(description="The note; null when it does not exist.")


class DailyAppended(BaseModel):
    date: str = Field(description="The day written, YYYY-MM-DD.")
    path: str = Field(description="Daily note that received the entry (created if it was missing).")
    entry: str = Field(description="The exact text appended.")


def _day(value: str | None) -> dt.date:
    """Parse a YYYY-MM-DD day (today when None), rejecting dates that do not exist."""
    if value is None:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise InvalidArgumentError(f"'{value}' is not a real date; use YYYY-MM-DD.") from None


def render_entry(content: str, tags: list[str], links: list[str], at: str | None) -> str:
    """Text for one entry: `content [[link]] #tag`, as `- HH:MM ...` when `at` is given."""
    text = content.strip()
    if at:
        text = text.replace("\n", "\n  ")  # continuation lines stay inside the bullet
    parts = [
        text,
        *(f"[[{link}]]" for link in links),
        *(f"#{tag.removeprefix('#')}" for tag in tags),
    ]
    entry = " ".join(parts)
    return f"- {at} {entry}" if at else entry


def register(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY)
    async def get_daily_note(date: Day = None) -> DailyNote:
        """Read the daily note for a day without creating it; exists=false when there is none.

        Use append_to_daily to write to it, get_note for any other note, list_vault_files to
        browse the daily folder.
        Example: get_daily_note(date="2026-11-22")
        """
        day = _day(date)
        vault = get_vault()
        note = await vault.read_daily(day)
        path = note.path if note else await vault.daily_path(day)
        return DailyNote(date=day.isoformat(), path=path, exists=note is not None, note=note)

    @server.tool(annotations=ADDITIVE)
    async def append_to_daily(
        content: Annotated[
            str, Field(min_length=1, pattern=r"\S", description="Entry text; must not be blank.")
        ],
        date: Day = None,
        heading: Annotated[
            str | None,
            Field(
                min_length=1,
                pattern=r"^[^\r\n]+$",
                description="Section to write under, e.g. 'Log' or '### Log'. Its end receives "
                "the entry; the heading is added at the end of the note when missing "
                "('## ' unless you give the #s). Omit to append at the end.",
            ),
        ] = None,
        timestamp: Annotated[
            bool,
            Field(description="True: write '- HH:MM content [[links]] #tags' (current time)."),
        ] = False,
        tags: Annotated[
            list[Tag] | None,
            Field(description="Inline #tags added after the content, with or without '#'."),
        ] = None,
        links: Annotated[
            list[LinkName] | None,
            Field(description="Notes to link, added as [[wikilinks]] after the content."),
        ] = None,
    ) -> DailyAppended:
        """Append an entry to a day's daily note, creating that day's note from the template.

        Use append_to_note for any other note, get_daily_note to read a day first.
        Entries land in the note of `date`, today when omitted, so past days work.
        Example: append_to_daily(content="Finished the report", date="2026-11-22", timestamp=true, tags=["work"])
        """
        day = _day(date)
        at = dt.datetime.now().strftime("%H:%M") if timestamp else None
        entry = render_entry(content, tags or [], links or [], at)
        path = await get_vault().append_daily(entry, day, heading.strip() if heading else None)
        return DailyAppended(date=day.isoformat(), path=path, entry=entry)
