"""Domain errors for Obsidian Brain MCP.

Every error subclasses `ToolError`, so one raised inside a tool call reaches the
model as `is_error=True` with its message and needs no per-tool try/except.
Messages are short and say what to do next. They never contain note content or the code and
payload sent to Obsidian; they name the path, heading, link or tag in question (vault-relative:
the vault's own absolute path is stripped), and cap any CLI output they quote.
"""

from mcp.server.mcpserver.exceptions import ToolError


class ObsidianError(ToolError):
    """Base class for every error this server raises on purpose."""


class CLINotFoundError(ObsidianError):
    """The Obsidian CLI binary cannot be located."""

    def __init__(self, searched_paths: str | None = None):
        message = (
            "Obsidian CLI not found. Install Obsidian 1.12.4+ from https://obsidian.md, "
            "enable Settings > General > Command line interface, click 'Register CLI', "
            "and restart the terminal (check with: obsidian version). "
            "Or set OBSIDIAN_CLI_PATH=/path/to/obsidian."
        )
        if searched_paths:
            message = f"Searched: {searched_paths}. {message}"
        super().__init__(message)


class ObsidianNotRunningError(ObsidianError):
    """The Obsidian desktop app is not running (the CLI talks to it over IPC)."""

    def __init__(self) -> None:
        super().__init__(
            "Obsidian is not running. Open the Obsidian desktop app, wait for the vault "
            "to load, then retry."
        )


class CLITimeoutError(ObsidianError):
    """A CLI subprocess exceeded its timeout and was killed."""

    def __init__(self, timeout: float, command: str):
        super().__init__(
            f"obsidian {command} timed out after {timeout:g}s and was stopped. Obsidian may "
            "still have carried the command out: check the vault before repeating a write."
        )


class ObsidianCLIError(ObsidianError):
    """The CLI failed: disabled, vault not found, or unexpected output."""


class NoteNotFoundError(ObsidianError):
    """A requested note, file or folder does not exist in the vault."""


class NoteExistsError(ObsidianError):
    """A note already exists and overwrite was not requested."""


class HeadingNotFoundError(ObsidianError):
    """The requested heading does not exist in the note."""


class InvalidArgumentError(ObsidianError):
    """An argument is invalid: bad path, date, tag, or a binary file read as text."""


class ContentTooLargeError(ObsidianError):
    """The payload exceeds what one CLI call can carry."""
