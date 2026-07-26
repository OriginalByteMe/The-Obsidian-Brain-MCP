"""
Tests for higher-level tool modules (knowledge, memory, onboarding).

Verifies that tool registration functions accept (server, VaultClient)
and that key tool behaviors work with a mocked VaultClient.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from obsidian_brain.exceptions import NoteNotFoundError
from obsidian_brain.protocol import VaultClient


class MockVaultClient:
    """Mock VaultClient that satisfies the Protocol.

    Mirrors real Obsidian CLI semantics: `create_note` dedupes to
    `<name> 1.<ext>` when the target already exists (never overwrites),
    while `update_note` always replaces the target path in place.
    """

    def __init__(self):
        self.created_notes: dict[str, str] = {}
        self.updated_notes: dict[str, str] = {}
        self.create_note_calls: list[str] = []
        self.update_note_calls: list[str] = []
        self.deleted_notes: list[str] = []
        self._notes: dict[str, dict[str, Any]] = {}
        self._files: list[str] = []

    async def list_directory(self, path: str = "/") -> list[dict[str, Any]]:
        return []

    async def get_all_files(self, path: str = "/") -> list[str]:
        return list(self._files)

    async def get_note(self, path: str) -> dict[str, Any]:
        if path in self._notes:
            return self._notes[path]
        raise NoteNotFoundError(path)

    async def note_exists(self, path: str) -> bool:
        return path in self._notes

    async def create_note(self, path: str, content: str) -> str:
        """Create at `path`; dedupes to '<name> 1.<ext>' if it already exists."""
        self.create_note_calls.append(path)
        actual_path = path
        if path in self._notes:
            base, sep, ext = path.rpartition(".")
            actual_path = f"{base} 1.{ext}" if sep else f"{path} 1"
        self.created_notes[actual_path] = content
        self._notes[actual_path] = {
            "content": content,
            "frontmatter": {},
            "tags": [],
        }
        if actual_path not in self._files:
            self._files.append(actual_path)
        return actual_path

    async def update_note(self, path: str, content: str) -> None:
        """Replace content at `path` in place, creating it if missing."""
        self.update_note_calls.append(path)
        self.updated_notes[path] = content
        self._notes[path] = {
            "content": content,
            "frontmatter": {},
            "tags": [],
        }
        if path not in self._files:
            self._files.append(path)

    async def append_to_note(self, path: str, content: str) -> None:
        self._notes[path]["content"] += content

    async def delete_note(self, path: str) -> None:
        if path not in self._notes:
            raise NoteNotFoundError(path)
        self.deleted_notes.append(path)
        self._notes.pop(path)
        self.created_notes.pop(path, None)
        if path in self._files:
            self._files.remove(path)

    async def search_simple(self, query: str) -> list[dict[str, Any]]:
        return []

    async def get_daily_path(self, date: str | None = None) -> str:
        return f"Daily/{date or '2026-01-01'}.md"

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
        client._notes["Obsidian Brain/knowledge-base.md"] = {
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
        assert data["path"] == "Obsidian Brain/knowledge-base.md"
        assert data["generator"] == "obsidian-brain-mcp"

    @pytest.mark.asyncio
    async def test_get_knowledge_base_status_stringifies_datetime_frontmatter(self):
        """A `created:`/`updated:` frontmatter value PyYAML parses into a
        datetime must not crash JSON serialization (regression)."""
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
        client._notes["Obsidian Brain/knowledge-base.md"] = {
            "content": "# Knowledge Base",
            "frontmatter": {
                "created": datetime(2026, 7, 26, 11, 28, 54),
                "updated": datetime(2026, 7, 26, 11, 28, 54),
                "generator": "obsidian-brain-mcp",
                "vault_stats": {"total_notes": 42},
            },
            "tags": [],
        }
        register_knowledge_tools(server, client)

        result = await tools["get_knowledge_base_status"]()
        data = json.loads(result)
        assert data["created"] == "2026-07-26T11:28:54"
        assert data["updated"] == "2026-07-26T11:28:54"


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
    async def test_list_memories_stringifies_datetime_frontmatter(self):
        """A `created:`/`updated:` frontmatter value PyYAML parses into a
        datetime must not crash JSON serialization (regression)."""
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
        path = "Obsidian Brain/memories/vault-overview.md"
        client._files.append(path)
        client._notes[path] = {
            "content": "Overview",
            "frontmatter": {
                "type": "overview",
                "created": datetime(2026, 7, 26, 11, 28, 54),
                "updated": datetime(2026, 7, 26, 11, 28, 54),
            },
            "tags": [],
        }
        register_memory_tools(server, client)

        result = await tools["list_memories"]()
        data = json.loads(result)
        assert data["memories"][0]["created"] == "2026-07-26T11:28:54"
        assert data["memories"][0]["updated"] == "2026-07-26T11:28:54"

    @pytest.mark.asyncio
    async def test_read_memory_stringifies_date_frontmatter(self):
        """A `due:`/`created:` frontmatter value PyYAML parses into a
        date/datetime must not crash JSON serialization (regression)."""
        from obsidian_brain.memory import memory_manager
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
        path = memory_manager.get_memory_path("test-memory")
        client._notes[path] = {
            "content": "Body",
            "frontmatter": {
                "created": datetime(2026, 7, 26, 11, 28, 54),
                "due": date(2026, 7, 26),
            },
            "tags": [],
        }
        register_memory_tools(server, client)

        result = await tools["read_memory"](name="test-memory")
        data = json.loads(result)
        assert data["created"] == "2026-07-26T11:28:54"
        assert data["frontmatter"]["due"] == "2026-07-26"

    @pytest.mark.asyncio
    async def test_write_memory_creates_note(self):
        """write_memory calls client.update_note with formatted content."""
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
        assert len(client.updated_notes) == 1
        assert client.create_note_calls == []
        # Verify the created note has frontmatter
        created_content = list(client.updated_notes.values())[0]
        assert "---" in created_content
        assert "This is a test memory" in created_content

    @pytest.mark.asyncio
    async def test_write_memory_replaces_existing_memory_in_place(self):
        """Writing over an existing memory must go through update_note, never
        dedupe via create_note (which would silently fork a '<name> 1.md')."""
        from obsidian_brain.memory import memory_manager
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

        await tools["write_memory"](name="test-memory", content="First body")
        path = memory_manager.get_memory_path("test-memory")

        result = await tools["write_memory"](name="test-memory", content="Second body")
        data = json.loads(result)
        assert data["success"] is True
        assert data["action"] == "updated"
        assert data["path"] == path
        assert client.create_note_calls == []
        assert client.update_note_calls == [path, path]
        assert client._files == [path]
        written = memory_manager.parse_memory(client.updated_notes[path], "test-memory")
        assert written.content == "Second body"

    @pytest.mark.asyncio
    async def test_memory_updates_preserve_frontmatter(self):
        from obsidian_brain.memory import memory_manager
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
        path = memory_manager.get_memory_path("test-memory")
        frontmatter = (
            "---\n"
            "created: original-created\n"
            "updated: original-updated\n"
            "type: learning\n"
            "aliases:\n"
            "- Durable context\n"
            "---\n\n"
        )
        client._notes[path] = {
            "content": "Old body",
            "raw": f"{frontmatter}Old body",
            "frontmatter": {},
            "tags": [],
        }
        register_memory_tools(server, client)

        await tools["write_memory"](name="test-memory", content="Replacement body")

        written = memory_manager.parse_memory(client.updated_notes[path], "test-memory")
        assert written.content == "Replacement body"
        assert written.frontmatter["created"] == "original-created"
        assert written.frontmatter["type"] == "learning"
        assert written.frontmatter["aliases"] == ["Durable context"]

        client._notes[path] = {
            "content": "Find this text",
            "raw": f"{frontmatter}Find this text",
            "frontmatter": {},
            "tags": [],
        }

        await tools["edit_memory"](
            name="test-memory",
            search="Find",
            replace="Keep",
        )

        edited = memory_manager.parse_memory(client.updated_notes[path], "test-memory")
        assert edited.content == "Keep this text"
        assert edited.frontmatter["created"] == "original-created"
        assert edited.frontmatter["type"] == "learning"
        assert edited.frontmatter["aliases"] == ["Durable context"]
        assert client.create_note_calls == []

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
    async def test_higher_level_writes_sync_cached_membership(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from obsidian_brain.cache import VaultCache
        from obsidian_brain.knowledge import KNOWLEDGE_BASE_PATH
        from obsidian_brain.onboarding import CONFIG_PATH, MEMORIES_PATH
        from obsidian_brain.tools import knowledge, memory, onboarding

        server = MagicMock()
        tools = {}

        def capture_tool():
            def decorator(fn):
                tools[fn.__name__] = fn
                return fn

            return decorator

        server.tool = capture_tool
        client = MockVaultClient()
        cache = VaultCache()
        await cache.refresh(client)
        monkeypatch.setattr(memory, "vault_cache", cache)
        monkeypatch.setattr(onboarding, "vault_cache", cache)
        monkeypatch.setattr(knowledge, "vault_cache", cache)
        memory.register_memory_tools(server, client)
        onboarding.register_onboarding_tools(server, client)
        knowledge.register_knowledge_tools(server, client)

        memory_path = f"{MEMORIES_PATH}/test.md"
        result = await tools["write_memory"](name="test", content="test content")
        assert json.loads(result)["success"] is True
        assert memory_path in cache.get_file_paths()
        assert memory_path in client.update_note_calls

        # Re-run write_memory on the now-existing memory: must replace it in
        # place via update_note, never fork a "<name> 1.md" via create_note.
        result = await tools["write_memory"](name="test", content="revised content")
        assert json.loads(result)["success"] is True
        assert json.loads(result)["action"] == "updated"
        assert client.update_note_calls.count(memory_path) == 2

        overview_path = f"{MEMORIES_PATH}/vault-overview.md"
        conventions_path = f"{MEMORIES_PATH}/conventions.md"

        result = await tools["run_onboarding"]()
        assert json.loads(result)["success"] is True
        assert "Obsidian Brain/config.md" in client.update_note_calls
        written_config = client._notes["Obsidian Brain/config.md"]["content"]
        assert written_config.startswith("```yaml\n")
        assert written_config.endswith("```\n")
        assert {
            CONFIG_PATH,
            overview_path,
            conventions_path,
        }.issubset(cache.get_file_paths())
        # config.md is a real markdown note now (the CLI rejects non-.md
        # extensions), so the cache has genuine metadata for it.
        config_metadata = cache.get_note_metadata(CONFIG_PATH)
        assert config_metadata is not None
        assert config_metadata.path == CONFIG_PATH

        # Re-run onboarding on the now-onboarded vault: every generated file
        # must be replaced in place via update_note, never deduped.
        result = await tools["run_onboarding"]()
        assert json.loads(result)["success"] is True
        assert client.update_note_calls.count(CONFIG_PATH) == 2
        assert client.update_note_calls.count(overview_path) == 2
        assert client.update_note_calls.count(conventions_path) == 2

        result = await tools["create_vault_knowledge_base"]()
        assert json.loads(result)["success"] is True
        assert KNOWLEDGE_BASE_PATH == "Obsidian Brain/knowledge-base.md"
        assert "Obsidian Brain/knowledge-base.md" in cache.get_file_paths()

        # Regenerate the knowledge base again: same fixed path, no duplicate.
        result = await tools["create_vault_knowledge_base"]()
        assert json.loads(result)["success"] is True
        assert client.update_note_calls.count("Obsidian Brain/knowledge-base.md") == 2

        # None of the create-or-replace flows above ever deduped via
        # create_note, and no path ever forked into "<name> 1.<ext>".
        assert client.create_note_calls == []
        assert not any(" 1" in f for f in client._files)

        result = await tools["delete_memory"](name="test")
        assert json.loads(result)["success"] is True
        assert memory_path not in cache.get_file_paths()


class TestOnboardingToolRegistration:
    """Tests for onboarding tool registration."""

    def test_register_onboarding_tools_accepts_server_and_client(self):
        """register_onboarding_tools accepts (server, VaultClient) without error."""
        from obsidian_brain.tools.onboarding import register_onboarding_tools

        server = MagicMock()
        server.tool.return_value = lambda fn: fn
        client = MockVaultClient()

        register_onboarding_tools(server, client)

    def test_config_path_is_cli_writable_md_file(self):
        """CONFIG_PATH is a literal .md path — the CLI rewrites any other extension."""
        from obsidian_brain.onboarding import CONFIG_PATH

        assert CONFIG_PATH == "Obsidian Brain/config.md"

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
    async def test_check_onboarding_finds_config_outside_file_listing(self):
        """The exact config-path probe must not depend on the cached file list."""
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
        assert data["config_path"] == "Obsidian Brain/config.md"

    @pytest.mark.asyncio
    async def test_check_onboarding_rejects_stale_yml_path(self):
        """A note at the old .yml path must not count as onboarded."""
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
        client._files = ["Obsidian Brain/config.yml"]
        client._notes["Obsidian Brain/config.yml"] = {"content": "version: 1"}
        register_onboarding_tools(server, client)

        result = await tools["check_onboarding_status"]()
        data = json.loads(result)
        assert data["onboarded"] is False

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

    @pytest.mark.asyncio
    async def test_get_vault_config_parses_fenced_yaml(self):
        """get_vault_config strips a ```yaml fence and returns parseable YAML."""
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
        client._notes[CONFIG_PATH] = {
            "content": "```yaml\nversion: '1.0'\nvault_profile:\n  depth_levels: 2\n```\n"
        }
        register_onboarding_tools(server, client)

        result = await tools["get_vault_config"]()
        data = json.loads(result)
        assert data["exists"] is True
        assert "```" not in data["content"]
        parsed = yaml.safe_load(data["content"])
        assert parsed["version"] == "1.0"
        assert parsed["vault_profile"]["depth_levels"] == 2

    @pytest.mark.asyncio
    async def test_get_vault_config_parses_bare_yaml(self):
        """A hand-edited config without a fence must still parse."""
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
        client._notes[CONFIG_PATH] = {
            "content": "version: '1.0'\nvault_profile:\n  depth_levels: 3\n"
        }
        register_onboarding_tools(server, client)

        result = await tools["get_vault_config"]()
        data = json.loads(result)
        assert data["exists"] is True
        parsed = yaml.safe_load(data["content"])
        assert parsed["version"] == "1.0"
        assert parsed["vault_profile"]["depth_levels"] == 3


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
