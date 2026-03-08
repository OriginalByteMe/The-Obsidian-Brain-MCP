"""
Obsidian Brain MCP Server

An MCP server that uses the Obsidian CLI to enable AI agents
to intelligently interact with Obsidian vaults.
"""

__version__ = "0.1.0"

from .cli_client import ObsidianCLIClient
from .exceptions import (
    CLINotFoundError,
    CLITimeoutError,
    NoteNotFoundError,
    ObsidianCLIError,
)
from .protocol import VaultClient

__all__ = [
    "ObsidianCLIClient",
    "VaultClient",
    "ObsidianCLIError",
    "NoteNotFoundError",
    "CLITimeoutError",
    "CLINotFoundError",
]
