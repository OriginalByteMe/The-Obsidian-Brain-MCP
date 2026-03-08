"""Tests for VaultClient Protocol definition."""

import inspect

import pytest

from obsidian_brain.protocol import VaultClient


class TestVaultClientProtocol:
    """Test that VaultClient Protocol is properly defined."""

    def test_protocol_has_all_expected_methods(self):
        """VaultClient Protocol must define all ~14 async methods."""
        expected_methods = [
            "list_directory",
            "get_all_files",
            "get_note",
            "note_exists",
            "create_note",
            "update_note",
            "append_to_note",
            "delete_note",
            "search_simple",
            "get_daily_note",
            "append_daily",
            "get_tags",
            "get_backlinks",
            "get_links",
        ]
        for method_name in expected_methods:
            assert hasattr(VaultClient, method_name), (
                f"VaultClient missing method: {method_name}"
            )

    def test_all_methods_are_async(self):
        """Every VaultClient method must be a coroutine function."""
        methods = [
            name
            for name, _ in inspect.getmembers(VaultClient, predicate=inspect.isfunction)
            if not name.startswith("_")
        ]
        for method_name in methods:
            method = getattr(VaultClient, method_name)
            assert inspect.iscoroutinefunction(method), (
                f"VaultClient.{method_name} must be async"
            )

    def test_protocol_is_runtime_checkable(self):
        """VaultClient must be decorated with @runtime_checkable."""

        class FakeClient:
            async def list_directory(self, path="/"):
                ...

            async def get_all_files(self, path="/"):
                ...

            async def get_note(self, path="", include_metadata=True):
                ...

            async def note_exists(self, path=""):
                ...

            async def create_note(self, path="", content=""):
                ...

            async def update_note(self, path="", content=""):
                ...

            async def append_to_note(self, path="", content=""):
                ...

            async def delete_note(self, path=""):
                ...

            async def search_simple(self, query="", context_length=100):
                ...

            async def get_daily_note(self, date=None):
                ...

            async def append_daily(self, content="", date=None):
                ...

            async def get_tags(self):
                ...

            async def get_backlinks(self, path=""):
                ...

            async def get_links(self, path=""):
                ...

        assert isinstance(FakeClient(), VaultClient)

    def test_non_conforming_class_fails_isinstance(self):
        """A class missing methods should NOT satisfy isinstance check."""

        class IncompleteClient:
            async def get_note(self, path=""):
                ...

        assert not isinstance(IncompleteClient(), VaultClient)

    def test_method_signatures(self):
        """Check key method signatures match expected types."""
        # get_note should have path and include_metadata params
        sig = inspect.signature(VaultClient.get_note)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "path" in params

        # search_simple should have query and context_length
        sig = inspect.signature(VaultClient.search_simple)
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "context_length" in params

        # get_daily_note should have optional date
        sig = inspect.signature(VaultClient.get_daily_note)
        params = list(sig.parameters.keys())
        assert "date" in params
