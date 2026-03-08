---
phase: 01-cli-migration
plan: 03
subsystem: tools
tags: [vaultclient, fastmcp, cache-invalidation, mcp-resources]

# Dependency graph
requires:
  - phase: 01-cli-migration/01
    provides: "VaultClient Protocol, ObsidianCLIClient, exceptions module"
provides:
  - "Knowledge/memory/onboarding tool modules migrated to VaultClient injection"
  - "Resource modules using FastMCP decorator API"
  - "VaultCache.invalidate_path() for targeted cache invalidation"
  - "21 tests covering higher-level tool registration and behavior"
affects: [01-cli-migration/04, server-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: ["VaultClient constructor injection in manager classes", "Targeted cache invalidation after write operations", "FastMCP resource decorator without uri= kwarg"]

key-files:
  created:
    - tests/test_tools_higher.py
  modified:
    - src/obsidian_brain/tools/knowledge.py
    - src/obsidian_brain/tools/memory.py
    - src/obsidian_brain/tools/onboarding.py
    - src/obsidian_brain/resources/structure.py
    - src/obsidian_brain/resources/knowledge.py
    - src/obsidian_brain/knowledge.py
    - src/obsidian_brain/memory.py
    - src/obsidian_brain/onboarding.py
    - src/obsidian_brain/cache.py

key-decisions:
  - "Manager classes kept as pure logic with optional VaultClient -- they were already client-agnostic"
  - "Added VaultCache.invalidate_path() for targeted invalidation instead of full cache refresh after writes"
  - "Used bare server parameter type (no string annotation) for compatibility with both MCPServer and FastMCP"

patterns-established:
  - "Tool registration: register_*_tools(server, client: VaultClient) signature for modules needing vault I/O"
  - "Resource registration: register_*_resource(server) for cache-only, register_*_resource(server, client) for vault I/O"
  - "Cache invalidation: check vault_cache.is_initialized before calling invalidate_path after writes"

requirements-completed: [TOOL-01, TOOL-03, TOOL-04, SDK-03]

# Metrics
duration: 8min
completed: 2026-03-08
---

# Phase 1 Plan 3: Higher-level Tools Summary

**Knowledge, memory, and onboarding tools migrated to VaultClient injection with targeted cache invalidation and FastMCP resource decorators**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-08T05:24:22Z
- **Completed:** 2026-03-08T05:32:00Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- All 3 higher-level tool modules (knowledge, memory, onboarding) accept injected VaultClient instead of creating ObsidianClient
- Both resource modules (structure, knowledge) use FastMCP-style decorator API
- Added targeted cache invalidation (VaultCache.invalidate_path) triggered after memory write/edit/delete operations
- 21 tests verify registration signatures, tool behaviors, cache invalidation, and absence of ObsidianClient references

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate manager classes to accept VaultClient** - `b55503c` (feat)
2. **Task 2: Migrate tool registration and resources, add tests** - `2094e78` (feat)

## Files Created/Modified
- `src/obsidian_brain/knowledge.py` - KnowledgeBaseManager accepts optional VaultClient
- `src/obsidian_brain/memory.py` - MemoryManager accepts optional VaultClient
- `src/obsidian_brain/onboarding.py` - OnboardingManager accepts optional VaultClient
- `src/obsidian_brain/tools/knowledge.py` - register_knowledge_tools(server, client) with VaultClient
- `src/obsidian_brain/tools/memory.py` - register_memory_tools(server, client) with cache invalidation
- `src/obsidian_brain/tools/onboarding.py` - register_onboarding_tools(server, client) with VaultClient
- `src/obsidian_brain/resources/structure.py` - FastMCP decorator format, cache-only (no client)
- `src/obsidian_brain/resources/knowledge.py` - FastMCP decorator format with VaultClient
- `src/obsidian_brain/cache.py` - Added invalidate_path() method
- `tests/test_tools_higher.py` - 21 tests for registration, behavior, cache invalidation

## Decisions Made
- **Manager classes kept as pure logic:** The plan assumed managers created ObsidianClient internally, but they were already client-agnostic pure transformers. Added optional VaultClient parameter for forward compatibility without restructuring.
- **Added VaultCache.invalidate_path():** Cache module lacked path-level invalidation. Added method that removes a note from cached structure and cleans backlink index references. Triggered after write_memory, edit_memory, delete_memory.
- **Bare server parameter type:** Used untyped `server` parameter instead of `FastMCP` type annotation, since Plan 01-02 (running in parallel) handles the MCPServer-to-FastMCP transition. Both types work.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added VaultCache.invalidate_path() method**
- **Found during:** Task 2 (memory tool migration)
- **Issue:** Plan requires cache invalidation after write operations (TOOL-03), but VaultCache had no path-level invalidation method
- **Fix:** Added invalidate_path() that removes note from cached notes list and cleans backlink index
- **Files modified:** src/obsidian_brain/cache.py
- **Verification:** test_write_memory_cache_invalidation passes
- **Committed in:** 2094e78

**2. [Rule 1 - Bug] Manager classes were already client-agnostic**
- **Found during:** Task 1 (manager migration)
- **Issue:** Plan assumed managers created ObsidianClient internally, but all 3 managers (KnowledgeBaseManager, MemoryManager, OnboardingManager) were already pure logic with no client references
- **Fix:** Added optional VaultClient constructor parameter for forward compatibility instead of the planned refactoring
- **Files modified:** knowledge.py, memory.py, onboarding.py
- **Verification:** Managers import and instantiate correctly, no ObsidianClient references
- **Committed in:** b55503c

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 plan assumption mismatch)
**Impact on plan:** Both deviations necessary. Cache invalidation was a requirement (TOOL-03). Manager simplification reduced work without affecting outcomes.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All higher-level tools and resources migrated, ready for Plan 01-04 (cache migration, cleanup, docs)
- The register_*_tools signatures now expect (server, client) -- server.py call sites need updating when Plan 01-02 changes land
- VaultCache.invalidate_path() available for any tool that writes to the vault

---
*Phase: 01-cli-migration*
*Completed: 2026-03-08*
