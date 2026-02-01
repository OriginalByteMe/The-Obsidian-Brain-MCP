# Act: Dynamic Vault Resources & Search Fix

**Status**: Complete

## Success Patterns → Formalization

### Pattern: MCP Resource Module Structure
**File**: `src/obsidian_brain/resources/vault_access.py`
**Description**: Template for creating new MCP resources with proper error handling
**When to use**: Adding new `vault://` resources

```python
def register_X_resources(server: "MCPServer") -> None:
    @server.resource(uri="vault://X/{path:path}", mime_type="...")
    async def get_X(path: str) -> str:
        async with ObsidianClient() as client:
            try:
                # Implementation
            except NoteNotFoundError:
                return "# Error: Not Found\n\n..."
            except ObsidianAPIError as e:
                return f"# Error: API Error\n\n{e.message}"
```

### Pattern: Cache-First with API Fallback
**File**: `src/obsidian_brain/resources/vault_access.py`
**Description**: Try cache for performance, fall back to API when unavailable
**When to use**: Resources that can benefit from cached data

```python
try:
    if vault_cache.is_initialized:
        # Use cached data (fast path)
        return cached_result
except CacheNotInitializedError:
    pass  # Fall through to API

# API fallback (slower but always works)
async with ObsidianClient() as client:
    return api_result
```

---

## Learnings → Global Rules

### Learning 1: pytest-httpx URL Pattern Matching
**Context**: Tests failed because httpx_mock matched exact URLs but API appends query params
**Insight**: Use `re.compile()` patterns for flexible URL matching in tests
**Action**: Document in test conventions

### Learning 2: Parallel Implementation Phases
**Context**: FR1 (search fix) and FR2 (note resource) had no dependencies
**Insight**: Identify independent phases early and execute concurrently
**Action**: Standard practice for multi-feature implementations

---

## Checklist Updates

### New Feature Checklist Items
- [x] Check if cache can optimize the feature (avoid repeated API calls)
- [x] Implement both cache path and API fallback path
- [x] Update server instructions with new tools/resources

### MCP Resource Checklist Items
- [x] Create resource function with proper type hints
- [x] Handle `NoteNotFoundError` gracefully
- [x] Handle `ObsidianAPIError` gracefully
- [x] Register resource in `server.py`
- [x] Add to Available Resources in server instructions

---

## Documentation Updates

- [x] Server instructions - Added new resources to Available Resources section
- [ ] README.md - Consider adding new resources to Available Tools table (optional)

---

## Follow-up Tasks

| Task | Priority | Notes |
|------|----------|-------|
| Add FolderListing Pydantic model | Low | Optional - current dict approach works fine |
| Integration tests with real vault | Medium | Would catch edge cases in folder traversal |

---

## Retrospective Summary

**What went well**:
- Clear design docs enabled fast implementation
- Parallel execution of independent phases
- Existing code patterns (structure.py) provided good templates
- All tests passing on first complete run after URL fix

**What could improve**:
- Document pytest-httpx query param behavior upfront
- Consider adding type hints for JSON response schemas

**Key takeaway**: Well-structured design documents with clear phase dependencies enable efficient parallel execution and reduce implementation time.
