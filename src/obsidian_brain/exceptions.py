"""
Shared exception hierarchy for Obsidian Brain MCP.

Provides structured errors for CLI subprocess failures,
note-not-found conditions, timeouts, and binary detection.
"""


class ObsidianCLIError(Exception):
    """Raised when an Obsidian CLI command fails (non-zero exit code).

    Attributes:
        returncode: Process exit code.
        stderr: Standard error output from the CLI process.
        command: The full command list that was executed.
    """

    def __init__(self, returncode: int, stderr: str, command: list[str]):
        self.returncode = returncode
        self.stderr = stderr
        self.command = command
        cmd_str = " ".join(command)
        super().__init__(
            f"CLI command failed (exit {returncode}): {cmd_str}\n{stderr}"
        )


class NoteNotFoundError(ObsidianCLIError):
    """Raised when a note does not exist in the vault.

    Attributes:
        path: The note path that was not found.
    """

    def __init__(self, path: str, command: list[str] | None = None):
        self.path = path
        super().__init__(
            returncode=1,
            stderr=f"Note not found: {path}",
            command=command or ["obsidian", "read", f'path="{path}"'],
        )


class CLITimeoutError(ObsidianCLIError):
    """Raised when a CLI subprocess exceeds its timeout.

    Attributes:
        timeout: The timeout value in seconds that was exceeded.
    """

    def __init__(self, timeout: float, command: list[str]):
        self.timeout = timeout
        super().__init__(
            returncode=-1,
            stderr=f"Command timed out after {timeout}s",
            command=command,
        )


class CLINotFoundError(Exception):
    """Raised when the Obsidian CLI binary cannot be located.

    This is NOT a CLI execution error -- it means the binary itself
    is missing from PATH and OBSIDIAN_CLI_PATH is not set.
    """

    def __init__(self, searched_paths: str | None = None):
        message = (
            "Obsidian CLI not found.\n\n"
            "To fix this:\n"
            "1. Install Obsidian 1.12.4+ from https://obsidian.md\n"
            "2. Enable CLI: Settings > General > Command line interface\n"
            "3. Click 'Register CLI' to add to PATH\n"
            "4. Restart your terminal\n"
            "5. Verify with: obsidian version\n\n"
            "Or set OBSIDIAN_CLI_PATH=/path/to/obsidian"
        )
        if searched_paths:
            message = f"Searched: {searched_paths}\n\n{message}"
        self.searched_paths = searched_paths
        super().__init__(message)
