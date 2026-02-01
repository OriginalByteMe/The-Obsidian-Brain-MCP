"""Tests for search tools."""

import json
import re

import pytest
from pytest_httpx import HTTPXMock

from obsidian_brain.tools.search import register_search_tools


class MockServer:
    """Mock MCP server for testing."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator


@pytest.fixture
def mock_server():
    """Create a mock server with registered search tools."""
    server = MockServer()
    register_search_tools(server)
    return server


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("OBSIDIAN_API_KEY", "test-key")
    monkeypatch.setenv("OBSIDIAN_HOST", "127.0.0.1")
    monkeypatch.setenv("OBSIDIAN_PORT", "27124")


# Pattern to match search URLs with query params
SEARCH_URL_PATTERN = re.compile(r"https://127\.0\.0\.1:27124/search/simple/\?.*")


class TestSearchContentContextExtraction:
    """Tests for search_content context extraction (FR1 bug fix)."""

    async def test_extracts_context_not_match_positions(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Verify context field is used instead of match position objects."""
        # API returns match positions AND context text
        httpx_mock.add_response(
            method="POST",
            url=SEARCH_URL_PATTERN,
            json=[
                {
                    "filename": "test.md",
                    "matches": [
                        {
                            "match": {"start": 10, "end": 20},  # Position data (old bug)
                            "context": "This is the actual context text",  # Actual text
                        }
                    ],
                    "score": 0.95,
                }
            ],
        )

        result = await mock_server.tools["search_content"]("test query")
        data = json.loads(result)

        assert data["success"] is True
        assert len(data["results"]) == 1
        # Should contain actual text, not position dict
        assert data["results"][0]["matches"][0] == "This is the actual context text"
        assert "start" not in data["results"][0]["matches"][0]

    async def test_handles_plain_string_matches(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Verify plain string matches are handled correctly."""
        httpx_mock.add_response(
            method="POST",
            url=SEARCH_URL_PATTERN,
            json=[
                {
                    "filename": "test.md",
                    "matches": ["plain string match"],
                    "score": 0.8,
                }
            ],
        )

        result = await mock_server.tools["search_content"]("test")
        data = json.loads(result)

        assert data["success"] is True
        assert data["results"][0]["matches"][0] == "plain string match"


class TestSearchContentMaxResults:
    """Tests for max_results parameter (FR4)."""

    async def test_limits_results_to_max(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Verify max_results limits the number of returned results."""
        # API returns 5 results
        httpx_mock.add_response(
            method="POST",
            url=SEARCH_URL_PATTERN,
            json=[
                {"filename": f"note{i}.md", "matches": [f"match {i}"], "score": 0.9 - i * 0.1}
                for i in range(5)
            ],
        )

        # Request only 2 results
        result = await mock_server.tools["search_content"]("test", max_results=2)
        data = json.loads(result)

        assert data["success"] is True
        assert len(data["results"]) == 2
        assert data["total_matches"] == 2

    async def test_returns_all_when_fewer_than_max(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Verify all results returned when fewer than max_results."""
        httpx_mock.add_response(
            method="POST",
            url=SEARCH_URL_PATTERN,
            json=[
                {"filename": "note1.md", "matches": ["match 1"], "score": 0.9},
            ],
        )

        result = await mock_server.tools["search_content"]("test", max_results=10)
        data = json.loads(result)

        assert data["success"] is True
        assert len(data["results"]) == 1


class TestSearchContentIncludeContent:
    """Tests for include_content parameter (FR4)."""

    async def test_fetches_content_when_enabled(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Verify full content is fetched when include_content=True."""
        # Search response
        httpx_mock.add_response(
            method="POST",
            url=SEARCH_URL_PATTERN,
            json=[
                {"filename": "test.md", "matches": ["snippet"], "score": 0.9},
            ],
        )
        # Note content response
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/test.md",
            text="# Test Note\n\nFull content here",
        )

        result = await mock_server.tools["search_content"](
            "test", include_content=True, max_results=10
        )
        data = json.loads(result)

        assert data["success"] is True
        assert len(data["results"]) == 1
        assert data["results"][0]["content"] == "# Test Note\n\nFull content here"

    async def test_no_content_when_disabled(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Verify content is not fetched when include_content=False."""
        httpx_mock.add_response(
            method="POST",
            url=SEARCH_URL_PATTERN,
            json=[
                {"filename": "test.md", "matches": ["snippet"], "score": 0.9},
            ],
        )

        result = await mock_server.tools["search_content"](
            "test", include_content=False, max_results=10
        )
        data = json.loads(result)

        assert data["success"] is True
        assert "content" not in data["results"][0]

    async def test_handles_content_fetch_error_gracefully(
        self, mock_server, mock_env, httpx_mock: HTTPXMock
    ):
        """Verify graceful handling when content fetch fails."""
        httpx_mock.add_response(
            method="POST",
            url=SEARCH_URL_PATTERN,
            json=[
                {"filename": "test.md", "matches": ["snippet"], "score": 0.9},
            ],
        )
        httpx_mock.add_response(
            method="GET",
            url="https://127.0.0.1:27124/vault/test.md",
            status_code=404,
        )

        result = await mock_server.tools["search_content"](
            "test", include_content=True, max_results=10
        )
        data = json.loads(result)

        assert data["success"] is True
        assert data["results"][0]["content"] is None


class TestSearchContentValidation:
    """Tests for input validation."""

    async def test_empty_query_returns_error(self, mock_server, mock_env):
        """Verify empty query returns validation error."""
        result = await mock_server.tools["search_content"]("")
        data = json.loads(result)

        assert data["error"] is True
        assert data["type"] == "ValidationError"

    async def test_whitespace_query_returns_error(self, mock_server, mock_env):
        """Verify whitespace-only query returns validation error."""
        result = await mock_server.tools["search_content"]("   ")
        data = json.loads(result)

        assert data["error"] is True
        assert data["type"] == "ValidationError"
