"""
Shared test fixtures for Obsidian Brain MCP tests.

Provides mock CLI subprocess results and sample JSON outputs
for testing parsers, CLI client, and protocol conformance.
"""

import json
from dataclasses import dataclass

import pytest


@dataclass
class MockProcessResult:
    """Fake subprocess result for testing."""

    stdout: bytes
    stderr: bytes
    returncode: int


def make_cli_output(data: dict | list | str, returncode: int = 0, stderr: str = "") -> MockProcessResult:
    """Create a fake CLI subprocess result.

    Args:
        data: JSON-serializable data for stdout, or raw string.
        returncode: Process exit code.
        stderr: Error output string.

    Returns:
        MockProcessResult with encoded bytes.
    """
    if isinstance(data, str):
        stdout = data.encode()
    else:
        stdout = json.dumps(data).encode()
    return MockProcessResult(
        stdout=stdout,
        stderr=stderr.encode(),
        returncode=returncode,
    )


@pytest.fixture
def mock_cli_output():
    """Fixture providing the make_cli_output helper."""
    return make_cli_output


@pytest.fixture
def sample_note_json() -> dict:
    """Sample CLI JSON output for a note read command."""
    return {
        "path": "Projects/MyProject.md",
        "content": "# My Project\n\nThis is my project notes.",
        "tags": ["project", "active"],
        "frontmatter": {
            "title": "My Project",
            "status": "active",
            "created": "2026-01-15",
        },
        "modified": "2026-03-01T10:30:00Z",
    }


@pytest.fixture
def sample_file_list_json() -> list:
    """Sample CLI JSON output for file listing command."""
    return [
        "Projects/MyProject.md",
        "Projects/Archive/OldProject.md",
        "Daily/2026-03-08.md",
        "README.md",
    ]


@pytest.fixture
def sample_search_json() -> list:
    """Sample CLI JSON output for search results."""
    return [
        {
            "path": "Projects/MyProject.md",
            "matches": ["This is my **project** notes."],
            "score": 0.95,
        },
        {
            "path": "Daily/2026-03-08.md",
            "matches": ["Working on **project** today."],
            "score": 0.75,
        },
    ]


@pytest.fixture
def sample_tags_json() -> dict:
    """Sample CLI JSON output for tags command."""
    return {
        "project": 5,
        "active": 3,
        "archive": 2,
        "daily": 15,
    }


@pytest.fixture
def sample_daily_json() -> dict:
    """Sample CLI JSON output for daily note read."""
    return {
        "content": "# 2026-03-08\n\n## Tasks\n- [ ] Write tests",
        "tags": ["daily"],
        "frontmatter": {
            "date": "2026-03-08",
        },
    }
