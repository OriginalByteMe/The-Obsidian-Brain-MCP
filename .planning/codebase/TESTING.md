# Testing Patterns

**Analysis Date:** 2026-03-08

## Test Framework

**Runner:**
- pytest >= 8.0.0 (dev dependency)
- Config: `pyproject.toml` under `[tool.pytest.ini_options]`

**Assertion Library:**
- pytest built-in assertions

**Async Support:**
- pytest-asyncio >= 0.23.0
- Mode: `asyncio_mode = "auto"` (all async test functions run automatically without `@pytest.mark.asyncio`)

**HTTP Mocking:**
- pytest-httpx >= 0.30.0 (for mocking httpx async client)

**Run Commands:**
```bash
pytest                    # Run all tests
pytest -v                 # Verbose output
pytest --tb=short         # Short tracebacks
pytest -x                 # Stop on first failure
# No coverage tool configured in dependencies
```

## Test File Organization

**Location:**
- Separate `tests/` directory at project root
- Test path configured: `testpaths = ["tests"]`

**Current State:**
- `tests/__init__.py` exists with only a docstring: `"""Tests for Obsidian Brain MCP."""`
- **No test files exist yet** - the test suite is empty

**Naming (prescriptive - follow these when adding tests):**
- Name test files `test_{module}.py` (pytest default discovery)
- Co-locate test utilities/fixtures in `tests/conftest.py`

**Expected Structure:**
```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures (create this)
├── test_client.py           # Tests for src/obsidian_brain/client.py
├── test_cache.py            # Tests for src/obsidian_brain/cache.py
├── test_models.py           # Tests for src/obsidian_brain/models.py
├── test_memory.py           # Tests for src/obsidian_brain/memory.py
├── test_onboarding.py       # Tests for src/obsidian_brain/onboarding.py
├── test_knowledge.py        # Tests for src/obsidian_brain/knowledge.py
├── utils/
│   ├── test_frontmatter.py  # Tests for src/obsidian_brain/utils/frontmatter.py
│   └── test_wikilinks.py    # Tests for src/obsidian_brain/utils/wikilinks.py
└── tools/
    ├── test_vault.py        # Tests for src/obsidian_brain/tools/vault.py
    ├── test_search.py       # Tests for src/obsidian_brain/tools/search.py
    ├── test_links.py        # Tests for src/obsidian_brain/tools/links.py
    ├── test_tags.py         # Tests for src/obsidian_brain/tools/tags.py
    ├── test_daily.py        # Tests for src/obsidian_brain/tools/daily.py
    ├── test_memory.py       # Tests for src/obsidian_brain/tools/memory.py
    ├── test_knowledge.py    # Tests for src/obsidian_brain/tools/knowledge.py
    └── test_onboarding.py   # Tests for src/obsidian_brain/tools/onboarding.py
```

## Test Structure

**Suite Organization (prescriptive):**
```python
"""Tests for the ObsidianClient HTTP wrapper."""

import pytest
from obsidian_brain.client import ObsidianClient, ObsidianAPIError, NoteNotFoundError


class TestObsidianClient:
    """Tests for ObsidianClient methods."""

    async def test_list_directory_returns_files(self, httpx_mock):
        """Test that list_directory returns parsed file entries."""
        httpx_mock.add_response(
            url="https://127.0.0.1:27124/vault/",
            json={"files": ["note.md", "folder/"]},
        )
        async with ObsidianClient(api_key="test") as client:
            result = await client.list_directory("/")
        assert len(result) == 2
        assert result[0]["type"] == "file"

    async def test_get_note_not_found_raises(self, httpx_mock):
        """Test that 404 raises NoteNotFoundError."""
        httpx_mock.add_response(status_code=404)
        async with ObsidianClient(api_key="test") as client:
            with pytest.raises(NoteNotFoundError):
                await client.get_note("missing.md")
```

**Patterns:**
- Group related tests in classes named `Test{Component}`
- Each test method is `async def test_{behavior}(self, ...)`
- Use descriptive test names that state expected behavior
- Use `asyncio_mode = "auto"` so no `@pytest.mark.asyncio` needed

## Mocking

**Framework:** pytest-httpx

**HTTP Mocking Pattern (prescriptive):**
```python
async def test_search_simple(self, httpx_mock):
    """Test simple text search returns formatted results."""
    httpx_mock.add_response(
        url="https://127.0.0.1:27124/search/simple/",
        json=[{
            "filename": "note.md",
            "matches": [{"match": "found text"}],
            "score": 1.0,
        }],
    )
    async with ObsidianClient(api_key="test") as client:
        results = await client.search_simple("query")
    assert len(results) == 1
```

**Mocking the Client in Tool Tests (prescriptive):**
Since tools create `ObsidianClient()` internally via context manager, mock at the httpx level using pytest-httpx rather than patching the client:
```python
async def test_tool_creates_note(self, httpx_mock):
    """Test create_note tool validates backlinks and creates note."""
    # Mock the note existence check
    httpx_mock.add_response(
        url="https://127.0.0.1:27124/vault/target.md",
        method="GET",
        text="target content",
    )
    # Mock the note creation
    httpx_mock.add_response(
        url="https://127.0.0.1:27124/vault/new-note.md",
        method="PUT",
        status_code=204,
    )
    # ... call tool and assert
```

**What to Mock:**
- All HTTP calls to Obsidian REST API (via pytest-httpx)
- Environment variables for `OBSIDIAN_API_KEY`, `OBSIDIAN_HOST`, `OBSIDIAN_PORT`

**What NOT to Mock:**
- Pydantic model validation
- Utility functions (`extract_wikilinks`, `parse_note`, `add_frontmatter_tags`)
- Cache logic (test with real `VaultCache` instances)
- Memory/Knowledge/Onboarding managers (pure logic, no I/O)

## Fixtures and Factories

**Recommended Fixtures (for `tests/conftest.py`):**
```python
import os
import pytest
from obsidian_brain.client import ObsidianClient
from obsidian_brain.models import NoteMetadata, VaultStructure, VaultStats, FolderNode
from obsidian_brain.cache import VaultCache


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("OBSIDIAN_API_KEY", "test-key")
    monkeypatch.setenv("OBSIDIAN_HOST", "127.0.0.1")
    monkeypatch.setenv("OBSIDIAN_PORT", "27124")


@pytest.fixture
def sample_note_metadata() -> NoteMetadata:
    """Create a sample NoteMetadata for testing."""
    return NoteMetadata(
        path="Projects/Test.md",
        title="Test",
        tags=["project", "test"],
        outgoing_links=["Reference"],
        incoming_links=[],
        frontmatter={"created": "2024-01-01"},
    )


@pytest.fixture
def sample_vault_structure(sample_note_metadata) -> VaultStructure:
    """Create a sample VaultStructure for testing."""
    return VaultStructure(
        folders=[FolderNode(name="Projects", path="Projects/")],
        notes=[sample_note_metadata],
        stats=VaultStats(total_notes=1, total_folders=1),
    )


@pytest.fixture
def populated_cache(sample_vault_structure) -> VaultCache:
    """Create a VaultCache with pre-populated structure."""
    cache = VaultCache()
    cache._structure = sample_vault_structure
    return cache
```

**Location:**
- Shared fixtures: `tests/conftest.py`
- Domain-specific fixtures: in test files or domain `conftest.py`

## Coverage

**Requirements:** None enforced - no coverage tool in dependencies

**To add coverage (recommended):**
```bash
# Add to dev dependencies
uv add --dev pytest-cov

# Run with coverage
pytest --cov=obsidian_brain --cov-report=term-missing
pytest --cov=obsidian_brain --cov-report=html
```

## Test Types

**Unit Tests (highest priority):**
- Pure utility functions in `src/obsidian_brain/utils/` - these have no I/O and are immediately testable
- Pydantic models in `src/obsidian_brain/models.py` - validation and serialization
- Manager logic in `src/obsidian_brain/memory.py`, `src/obsidian_brain/onboarding.py`, `src/obsidian_brain/knowledge.py` - pure data transformation
- Cache logic in `src/obsidian_brain/cache.py` - data structure operations

**Integration Tests (medium priority):**
- Tool functions in `src/obsidian_brain/tools/` - require mocking HTTP via pytest-httpx
- Client methods in `src/obsidian_brain/client.py` - require mocking HTTP responses
- Resource handlers in `src/obsidian_brain/resources/` - require mocking HTTP

**E2E Tests:**
- Not used - would require a running Obsidian instance with Local REST API plugin

## Common Patterns

**Async Testing:**
```python
# asyncio_mode = "auto" means no decorator needed
async def test_async_operation():
    """Async tests run automatically."""
    async with ObsidianClient(api_key="test") as client:
        result = await client.some_method()
    assert result is not None
```

**Error Testing:**
```python
async def test_not_found_raises_error(self, httpx_mock):
    """Test that missing notes raise NoteNotFoundError."""
    httpx_mock.add_response(status_code=404)
    async with ObsidianClient(api_key="test") as client:
        with pytest.raises(NoteNotFoundError) as exc_info:
            await client.get_note("missing.md")
    assert exc_info.value.status_code == 404
    assert "missing.md" in str(exc_info.value)
```

**Testing Tool JSON Responses:**
```python
import json

async def test_tool_returns_error_json(self, httpx_mock):
    """Test that tool returns structured error JSON."""
    httpx_mock.add_response(status_code=404)
    result = await some_tool("missing.md")
    data = json.loads(result)
    assert data["error"] is True
    assert data["type"] == "NoteNotFoundError"
```

**Testing Pure Utilities (no mocking needed):**
```python
from obsidian_brain.utils.wikilinks import extract_wikilinks, contains_wikilink

class TestExtractWikilinks:
    def test_extracts_simple_link(self):
        assert extract_wikilinks("See [[Note A]]") == ["Note A"]

    def test_extracts_aliased_link(self):
        assert extract_wikilinks("[[Note|alias]]") == ["Note"]

    def test_extracts_multiple_links(self):
        result = extract_wikilinks("[[A]] and [[B]]")
        assert result == ["A", "B"]

    def test_empty_content_returns_empty(self):
        assert extract_wikilinks("") == []
```

**Testing Frontmatter Utilities:**
```python
from obsidian_brain.utils.frontmatter import parse_note, add_frontmatter_tags

class TestParseNote:
    def test_parses_frontmatter_and_body(self):
        content = "---\ntags: [a, b]\n---\n# Title\nBody"
        fm, body = parse_note(content)
        assert fm["tags"] == ["a", "b"]
        assert "Title" in body

class TestAddFrontmatterTags:
    def test_adds_new_tags(self):
        content = "---\ntags: [a]\n---\nBody"
        result = add_frontmatter_tags(content, ["b", "c"])
        assert "b" in result
        assert "c" in result
```

## Immediately Testable Components

These components have pure logic with no I/O dependencies and should be tested first:

1. **`src/obsidian_brain/utils/wikilinks.py`** - All functions are pure: `extract_wikilinks`, `contains_wikilink`, `inject_wikilink`, `create_wikilink`, `resolve_wikilink`, `normalize_note_name`
2. **`src/obsidian_brain/utils/frontmatter.py`** - All functions are pure: `parse_note`, `get_frontmatter`, `add_frontmatter_tags`, `remove_frontmatter_tags`, `create_note_with_frontmatter`, `merge_frontmatter`, `has_frontmatter`, `ensure_frontmatter`
3. **`src/obsidian_brain/models.py`** - Pydantic model creation and serialization
4. **`src/obsidian_brain/memory.py`** - `MemoryManager` methods: `get_memory_path`, `_sanitize_name`, `parse_memory`, `create_memory_content`, `update_memory_content`, `list_from_files`, `format_memory_list`
5. **`src/obsidian_brain/onboarding.py`** - `OnboardingManager` analysis methods (take `VaultStructure` as input)
6. **`src/obsidian_brain/knowledge.py`** - `KnowledgeBaseManager.generate_content` and all `_build_*` methods
7. **`src/obsidian_brain/cache.py`** - `VaultCache` getter methods (after manually setting `_structure`)

---

*Testing analysis: 2026-03-08*
