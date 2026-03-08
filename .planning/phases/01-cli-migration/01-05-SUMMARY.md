---
phase: 01-cli-migration
plan: 05
subsystem: api
tags: [python, fastmcp, wiring, dependency-injection, cli]
requires:
  - phase: 01-cli-migration
    provides: Tool/resource modules migrated to accept VaultClient
provides:
  - Correct tool/resource registration wiring for onboarding and knowledge modules
  - Consistent client singleton injection across all client-dependent registrations
affects: [phase-03-plugin-layer, server-startup, runtime-stability]
tech-stack:
  added: []
  patterns: [register-functions-receive-shared-client-singleton]
key-files:
  created: []
  modified: [src/obsidian_brain/server.py]
key-decisions:
  - "Keep register_structure_resource as single-arg registration because it is cache-only and does not require VaultClient."
  - "Enforce consistent two-arg registration for all client-dependent tool/resource modules."
patterns-established:
  - "Server wiring pattern: register_xxx(mcp, client) for every module that performs vault operations."
requirements-completed: [SDK-01, SDK-02, SDK-03, SDK-04, SDK-05, CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, CLI-07, CLI-08, TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05]
duration: 4min
completed: 2026-03-08
---

# Phase 01 Plan 05: Registration Wiring Fix Summary

**Server registration wiring now passes the VaultClient singleton to onboarding tools and the knowledge resource, removing runtime invocation crashes.**

## Performance

- **Duration:** 4min
- **Started:** 2026-03-08T05:56:11Z
- **Completed:** 2026-03-08T06:00:11Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Fixed `register_onboarding_tools` registration to pass `client`.
- Fixed `register_knowledge_resource` registration to pass `client`.
- Verified all client-dependent registrations in `server.py` use the two-argument wiring pattern.

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix server.py wiring bugs for onboarding tools and knowledge resource** - `ec92857` (fix)

## Files Created/Modified
- `src/obsidian_brain/server.py` - Corrected onboarding/knowledge registration calls to pass shared client singleton.

## Decisions Made
- Kept `register_structure_resource(mcp)` unchanged because the structure resource is cache-only and does not require the vault client.
- Applied a strict consistency check that all other registration calls requiring vault operations pass `client`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Runtime crash risk from missing client injection in onboarding/knowledge registrations is removed.
- Phase is ready for closeout and downstream verification with full registration consistency.

## Self-Check: PASSED
- FOUND: `.planning/phases/01-cli-migration/01-05-SUMMARY.md`
- FOUND commit: `ec92857`

---
*Phase: 01-cli-migration*
*Completed: 2026-03-08*
