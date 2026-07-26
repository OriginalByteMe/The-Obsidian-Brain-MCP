"""Shared pytest configuration for the Obsidian Brain MCP test suite."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "real_cli: opt-in end-to-end test against the real obsidian-cli binary and a running "
        "Obsidian app (select with '-m real_cli', deselect with '-m \"not real_cli\"').",
    )
