"""
Tests for the FastMCP server initialization and tool registration.
"""

import importlib
import os
import subprocess
import sys

from mcp.server.fastmcp import FastMCP


class TestServerInit:
    """Test FastMCP server initializes correctly."""

    def test_mcp_is_fastmcp_instance(self):
        """Server object is a FastMCP instance."""
        from obsidian_brain.server import mcp

        assert isinstance(mcp, FastMCP)

    def test_mcp_name(self):
        """Server has correct name."""
        from obsidian_brain.server import mcp

        assert mcp.name == "obsidian-brain"

    def test_client_is_cli_client(self):
        """Client singleton is an ObsidianCLIClient."""
        from obsidian_brain.cli_client import ObsidianCLIClient
        from obsidian_brain.server import client

        assert isinstance(client, ObsidianCLIClient)

    def test_server_imports_without_installed_cli(self):
        """Importing the server must not require Obsidian to be installed."""
        env = os.environ.copy()
        env["PATH"] = ""
        _ = env.pop("OBSIDIAN_CLI_PATH", None)
        result = subprocess.run(
            [sys.executable, "-c", "import obsidian_brain.server"],
            capture_output=True,
            env=env,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr

    def test_main_is_callable(self):
        """main() function exists and is callable."""
        from obsidian_brain.server import main

        assert callable(main)

    def test_server_has_instructions(self):
        """Server has non-empty instructions."""
        from obsidian_brain.server import mcp

        assert mcp.instructions
        assert len(mcp.instructions) > 100

    def test_instructions_mention_cli(self):
        """Server instructions reference CLI requirements."""
        from obsidian_brain.server import mcp

        assert "CLI" in mcp.instructions or "cli" in mcp.instructions.lower()

    def test_instructions_no_rest_api(self):
        """Server instructions do not mention REST API."""
        from obsidian_brain.server import mcp

        assert "REST API" not in mcp.instructions
        assert "OBSIDIAN_API_KEY" not in mcp.instructions

    def test_instructions_no_removed_tools(self):
        """Server instructions do not list removed tools."""
        from obsidian_brain.server import mcp

        assert "search_advanced" not in mcp.instructions
        assert "search_jsonlogic" not in mcp.instructions
        assert "get_periodic_note" not in mcp.instructions


class TestNoMcpUse:
    """Verify no mcp_use imports exist in src/."""

    def test_no_mcp_use_in_core_tools(self):
        """Core tool modules do not import mcp_use."""
        core_modules = [
            "obsidian_brain.tools.vault",
            "obsidian_brain.tools.links",
            "obsidian_brain.tools.tags",
            "obsidian_brain.tools.search",
            "obsidian_brain.tools.daily",
        ]
        for mod_name in core_modules:
            mod = importlib.import_module(mod_name)
            source_file = mod.__file__
            assert source_file is not None
            with open(source_file) as f:
                source = f.read()
            assert "mcp_use" not in source, f"mcp_use found in {mod_name}"

    def test_no_mcp_use_in_server(self):
        """Server module does not import mcp_use."""
        import obsidian_brain.server as srv

        source_file = srv.__file__
        assert source_file is not None
        with open(source_file) as f:
            source = f.read()
        assert "mcp_use" not in source


class TestToolRegistration:
    """Test that tool registration functions work with FastMCP + VaultClient."""

    def test_register_vault_tools_callable(self):
        """register_vault_tools accepts FastMCP and VaultClient."""
        from obsidian_brain.tools.vault import register_vault_tools

        assert callable(register_vault_tools)

    def test_register_link_tools_callable(self):
        """register_link_tools accepts FastMCP and VaultClient."""
        from obsidian_brain.tools.links import register_link_tools

        assert callable(register_link_tools)

    def test_register_tag_tools_callable(self):
        """register_tag_tools accepts FastMCP and VaultClient."""
        from obsidian_brain.tools.tags import register_tag_tools

        assert callable(register_tag_tools)

    def test_register_search_tools_callable(self):
        """register_search_tools accepts FastMCP and VaultClient."""
        from obsidian_brain.tools.search import register_search_tools

        assert callable(register_search_tools)

    def test_register_daily_tools_callable(self):
        """register_daily_tools accepts FastMCP and VaultClient."""
        from obsidian_brain.tools.daily import register_daily_tools

        assert callable(register_daily_tools)
