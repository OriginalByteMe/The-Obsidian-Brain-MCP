# Plan: Dynamic Vault Resources & Search Fix

**Created**: 2026-01-30
**Source**: `docs/design-dynamic-resources.md`, `docs/workflow_dynamic_resources.md`

## Hypothesis

We need to implement four feature requests to improve vault accessibility:

1. **FR1**: Fix search_content bug - extracts position data instead of text context
2. **FR2**: Add `vault://note/{path}` dynamic resource for direct note access
3. **FR3**: Add `vault://folder/{path}` dynamic resource for folder listings
4. **FR4**: Enhance search with `include_content` and `max_results` parameters

**Why this approach**: The design documents specify a phased implementation strategy with clear dependencies. FR1 is critical and quick. FR2 and FR3 are independent and high-value. FR4 builds on FR1.

## Expected Outcomes (Quantitative)

| Metric | Expected | Notes |
|--------|----------|-------|
| Search bug fixed | 100% | Single line change |
| Note resource functional | Yes | Direct note access via MCP |
| Folder resource functional | Yes | Recursive listing with cache |
| Tests passing | 100% | Unit tests for new functionality |
| No regressions | Yes | Existing functionality preserved |

## Phases

### Phase 1: Search Bug Fix (FR1)
- **File**: `src/obsidian_brain/tools/search.py`
- **Change**: Line 62 - `m.get("match")` → `m.get("context")`
- **Risk**: Low - single line, backwards compatible

### Phase 2: Dynamic Note Resource (FR2)
- **New file**: `src/obsidian_brain/resources/vault_access.py`
- **Modify**: `src/obsidian_brain/server.py` (import + registration)
- **Risk**: Low - additive change

### Phase 3: Dynamic Folder Resource (FR3)
- **Extend**: `src/obsidian_brain/resources/vault_access.py`
- **Modify**: `src/obsidian_brain/server.py` (instructions)
- **Risk**: Medium - depends on cache understanding

### Phase 4: Enhanced Search (FR4)
- **Modify**: `src/obsidian_brain/tools/search.py`
- **Add**: `include_content`, `max_results` parameters
- **Risk**: Low - builds on FR1 fix

### Phase 5: Testing
- **New**: `tests/test_search.py`, `tests/test_resources.py`
- **Coverage**: Search and resource functionality

## Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Cache not initialized | Implement API fallback in folder resource |
| Large folders | Add warning in response when >100 notes |
| API errors | Graceful error handling with informative messages |
| Breaking changes | All changes are additive except FR1 (single line) |

## Rollback Plan

- New resources: Remove imports from `server.py`
- Search fix: Revert single word change (`context` → `match`)
- No database migrations or breaking changes
