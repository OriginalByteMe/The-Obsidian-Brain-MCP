"""
Tests for higher-level tool modules (knowledge, memory, onboarding).

Verifies that tool registration functions accept (server, VaultClient)
and that key tool behaviors work with a mocked VaultClient.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from obsidian_brain.exceptions import NoteNotFoundError
from obsidian_brain.protocol import VaultClient


class MockVaultClient:
    """Mock VaultClient that satisfies the Protocol."""

    def __init__(self):
        self.created_notes: dict[str, str] = {}
        self.deleted_notes: list[str] = []
        self._notes: dict[str, dict[str, Any]] = {}
        self._files: list[str] = []

    async def list_directory(self, path: str = "/") -> list[dict[str, Any]]:
        return []

    async def get_all_files(self, path: str = "/") -> list[str]:
        return list(self._files)

    async def get_note(self, path: str, include_metadata: bool = True) -> dict[str, Any]:
        if path in self._notes:
            return self._notes[path]
        raise NoteNotFoundError(path)

    async def note_exists(self, path: str) -> bool:
        return path in self._notes

    async def create_note(self, path: str, content: str) -> None:
        self.created_notes[path] = content

    async def update_note(self, path: str, content: str) -> None:
        self.created_notes[path] = content

    async def append_to_note(self, path: str, content: str) -> None:
        pass

    async def delete_note(self, path: str) -> None:
        if path not in self._notes and path not in self.created_notes:
            raise NoteNotFoundError(path)
        self.deleted_notes.append(path)

    async def search_simple(self, query: str, context_length: int = 100) -> list[dict[str, Any]]:
        return []

    async def get_daily_note(self, date: str | None = None) -> dict[str, Any]:
        return {"content": "", "tags": [], "frontmatter": {}}

    async def append_daily(self, content: str, date: str | None = None) -> None:
        pass

    async def get_tags(self) -> dict[str, int]:
        return {}

    async def get_backlinks(self, path: str) -> list[str]:
        return []

    async def get_links(self, path: str) -> list[str]:
        return []


def test_mock_satisfies_protocol():
    """MockVaultClient satisfies VaultClient Protocol."""
    client = MockVaultClient()
    assert isinstance(client, VaultClient)


class TestKnowledgeToolRegistration:
    """Tests for knowledge tool registration."""

    def test_register_knowledge_tools_accepts_server_and_client(self):
        """register_knowledge_tools accepts (server, VaultClient) without error."""
        from obsidian_brain.tools.knowledge import register_knowledge_tools

        server = MagicMock()
        server.tool.return_value = lambda fn: fn
        client = MockVaultClient()

        # Should not raise
        register_knowledge_tools(server, client)

    @pytest.mark.asyncio
    async def test_get_knowledge_base_status_not_found(self):
        """get_knowledge_base_status returns not-found when KB doesn't exist."""
        from obsidian_brain.tools.knowledge import register_knowledge_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        register_knowledge_tools(server, client)

        result = await tools["get_knowledge_base_status"]()
        data = json.loads(result)
        assert data["exists"] is False
        assert "recommendation" in data

    @pytest.mark.asyncio
    async def test_get_knowledge_base_status_found(self):
        """get_knowledge_base_status returns info when KB exists."""
        from obsidian_brain.tools.knowledge import register_knowledge_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        client._notes[".obsidian-brain/knowledge-base.md"] = {
            "content": "# Knowledge Base",
            "frontmatter": {
                "created": "2026-01-01",
                "updated": "2026-03-01",
                "generator": "obsidian-brain-mcp",
                "vault_stats": {"total_notes": 42},
            },
            "tags": [],
        }
        register_knowledge_tools(server, client)

        result = await tools["get_knowledge_base_status"]()
        data = json.loads(result)
        assert data["exists"] is True
        assert data["generator"] == "obsidian-brain-mcp"


class TestMemoryToolRegistration:
    """Tests for memory tool registration."""

    def test_register_memory_tools_accepts_server_and_client(self):
        """register_memory_tools accepts (server, VaultClient) without error."""
        from obsidian_brain.tools.memory import register_memory_tools

        server = MagicMock()
        server.tool.return_value = lambda fn: fn
        client = MockVaultClient()

        register_memory_tools(server, client)

    @pytest.mark.asyncio
    async def test_write_memory_creates_note(self):
        """write_memory calls client.create_note with formatted content."""
        from obsidian_brain.tools.memory import register_memory_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        register_memory_tools(server, client)

        result = await tools["write_memory"](
            name="test-memory",
            content="This is a test memory",
            memory_type="test",
        )
        data = json.loads(result)
        assert data["success"] is True
        assert data["action"] == "created"
        assert len(client.created_notes) == 1
        # Verify the created note has frontmatter
        created_content = list(client.created_notes.values())[0]
        assert "---" in created_content
        assert "This is a test memory" in created_content

    @pytest.mark.asyncio
    async def test_list_memories_returns_empty(self):
        """list_memories returns empty list when no memories exist."""
        from obsidian_brain.tools.memory import register_memory_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        register_memory_tools(server, client)

        result = await tools["list_memories"]()
        data = json.loads(result)
        assert data["count"] == 0
        assert data["memories"] == []

    @pytest.mark.asyncio
    async def test_list_memories_returns_existing(self):
        """list_memories returns memories from file listing."""
        from obsidian_brain.tools.memory import register_memory_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        client._files = [
            "Obsidian Brain/memories/vault-overview.md",
            "Obsidian Brain/memories/conventions.md",
            "other/file.md",
        ]
        client._notes["Obsidian Brain/memories/vault-overview.md"] = {
            "content": "# Overview",
            "frontmatter": {"type": "vault-overview", "created": "2026-01-01"},
            "tags": [],
        }
        client._notes["Obsidian Brain/memories/conventions.md"] = {
            "content": "# Conventions",
            "frontmatter": {"type": "conventions", "created": "2026-01-01"},
            "tags": [],
        }
        register_memory_tools(server, client)

        result = await tools["list_memories"]()
        data = json.loads(result)
        assert data["count"] == 2

    @pytest.mark.asyncio
    async def test_delete_memory_calls_delete(self):
        """delete_memory calls client.delete_note."""
        from obsidian_brain.tools.memory import register_memory_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        path = "Obsidian Brain/memories/test-memory.md"
        client._notes[path] = {"content": "test", "frontmatter": {}}
        register_memory_tools(server, client)

        result = await tools["delete_memory"](name="test-memory")
        data = json.loads(result)
        assert data["success"] is True
        assert path in client.deleted_notes

    @pytest.mark.asyncio
    async def test_delete_memory_not_found(self):
        """delete_memory returns error when memory doesn't exist."""
        from obsidian_brain.tools.memory import register_memory_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        register_memory_tools(server, client)

        result = await tools["delete_memory"](name="nonexistent")
        data = json.loads(result)
        assert data["error"] is True
        assert data["type"] == "MemoryNotFoundError"

    @pytest.mark.asyncio
    async def test_write_memory_cache_invalidation(self):
        """write_memory invalidates cache after writing."""
        from obsidian_brain.cache import vault_cache
        from obsidian_brain.tools.memory import register_memory_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        register_memory_tools(server, client)

        # Mock cache as initialized with invalidate_path
        with (
            patch.object(
                type(vault_cache), "is_initialized", new_callable=PropertyMock, return_value=True
            ),
            patch.object(vault_cache, "invalidate_path") as mock_invalidate,
        ):
            result = await tools["write_memory"](
                name="test",
                content="test content",
            )
            data = json.loads(result)
            assert data["success"] is True
            mock_invalidate.assert_called_once()


class TestOnboardingToolRegistration:
    """Tests for onboarding tool registration."""

    def test_register_onboarding_tools_accepts_server_and_client(self):
        """register_onboarding_tools accepts (server, VaultClient) without error."""
        from obsidian_brain.tools.onboarding import register_onboarding_tools

        server = MagicMock()
        server.tool.return_value = lambda fn: fn
        client = MockVaultClient()

        register_onboarding_tools(server, client)

    @pytest.mark.asyncio
    async def test_check_onboarding_not_onboarded(self):
        """check_onboarding_status returns not-onboarded for empty vault."""
        from obsidian_brain.tools.onboarding import register_onboarding_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        register_onboarding_tools(server, client)

        result = await tools["check_onboarding_status"]()
        data = json.loads(result)
        assert data["onboarded"] is False

    @pytest.mark.asyncio
    async def test_check_onboarding_finds_yaml_config_outside_markdown_listing(self):
        """The exact config check must not depend on the Markdown-only file list."""
        from obsidian_brain.onboarding import CONFIG_PATH
        from obsidian_brain.tools.onboarding import register_onboarding_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        client._files = ["Obsidian Brain/memories/conventions.md", "Inbox.md"]
        client._notes[CONFIG_PATH] = {"content": "version: 1"}
        register_onboarding_tools(server, client)

        result = await tools["check_onboarding_status"]()
        data = json.loads(result)
        assert data["onboarded"] is True
        assert data["config_path"] == CONFIG_PATH

    @pytest.mark.asyncio
    async def test_get_vault_config_not_found(self):
        """get_vault_config returns not-found when not onboarded."""
        from obsidian_brain.tools.onboarding import register_onboarding_tools

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        register_onboarding_tools(server, client)

        result = await tools["get_vault_config"]()
        data = json.loads(result)
        assert data["exists"] is False


class TestResourceRegistration:
    """Tests for resource module registration."""

    def test_register_structure_resource(self):
        """register_structure_resource accepts server without error."""
        from obsidian_brain.resources.structure import register_structure_resource

        server = MagicMock()
        server.resource.return_value = lambda fn: fn

        register_structure_resource(server)

    def test_register_knowledge_resource(self):
        """register_knowledge_resource accepts (server, VaultClient) without error."""
        from obsidian_brain.resources.knowledge import register_knowledge_resource

        server = MagicMock()
        server.resource.return_value = lambda fn: fn
        client = MockVaultClient()

        register_knowledge_resource(server, client)


class TestNoObsidianClientImports:
    """Verify no ObsidianClient references remain in migrated modules."""

    def test_no_obsidian_client_in_tool_knowledge(self):
        """tools/knowledge.py has no ObsidianClient references."""
        import inspect
        from obsidian_brain.tools import knowledge

        source = inspect.getsource(knowledge)
        assert "ObsidianClient" not in source

    def test_no_obsidian_client_in_tool_memory(self):
        """tools/memory.py has no ObsidianClient references."""
        import inspect
        from obsidian_brain.tools import memory

        source = inspect.getsource(memory)
        assert "ObsidianClient" not in source

    def test_no_obsidian_client_in_tool_onboarding(self):
        """tools/onboarding.py has no ObsidianClient references."""
        import inspect
        from obsidian_brain.tools import onboarding

        source = inspect.getsource(onboarding)
        assert "ObsidianClient" not in source

    def test_no_obsidian_client_in_resource_structure(self):
        """resources/structure.py has no ObsidianClient references."""
        import inspect
        from obsidian_brain.resources import structure

        source = inspect.getsource(structure)
        assert "ObsidianClient" not in source

    def test_no_obsidian_client_in_resource_knowledge(self):
        """resources/knowledge.py has no ObsidianClient references."""
        import inspect
        from obsidian_brain.resources import knowledge

        source = inspect.getsource(knowledge)
        assert "ObsidianClient" not in source
