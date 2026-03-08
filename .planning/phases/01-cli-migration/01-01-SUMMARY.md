---
phase: 01-cli-migration
plan: 01
subsystem: api
tags: [protocol, subprocess, asyncio, cli, parsers, exceptions]

# Dependency graph
requires:
  - phase: 01-00
    provides: pre-migration snapshot tests as migration contract
provides:
  - VaultClient Protocol with 14 async methods
  - ObsidianCLIClient implementing VaultClient via asyncio subprocess
  - CLI JSON output parsers (note, file_list, search, tags, daily)
  - Shared exception hierarchy (ObsidianCLIError, NoteNotFoundError, CLITimeoutError, CLINotFoundError)
  - Test infrastructure with mocked subprocess fixtures
affects: [01-02, 01-03, 01-04]

# Tech tracking
tech-stack:
  added: [pytest-asyncio, pytest-timeout]
  patterns: [VaultClient Protocol, async subprocess exec, defensive JSON parsing]

key-files:
  created:
    - src/obsidian_brain/protocol.py
    - src/obsidian_brain/cli_client.py
    - src/obsidian_brain/parsers.py
    - src/obsidian_brain/exceptions.py
    - tests/conftest.py
    - tests/test_protocol.py
    - tests/test_parsers.py
    - tests/test_cli_client.py
  modified: []

key-decisions:
  - "VaultClient Protocol uses runtime_checkable for isinstance conformance checks"
  - "Parsers accept both dict and JSON string inputs for flexibility"
  - "CLINotFoundError is separate from ObsidianCLIError (not a CLI execution failure)"
  - "Path sanitization rejects null bytes; list-form exec handles shell injection"

patterns-established:
  - "VaultClient Protocol: all vault operations coded against Protocol, not concrete class"
  - "Defensive parsing: .get() with defaults, handle multiple possible JSON shapes"
  - "Subprocess pattern: asyncio.create_subprocess_exec with list-form args, asyncio.wait_for timeout"
  - "Test pattern: mock asyncio.create_subprocess_exec to return fake Process objects"

requirements-completed: [CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, CLI-08, SDK-05]

# Metrics
duration: 8min
completed: 2026-03-08
---

# Phase 1 Plan 01: Foundation Summary

**VaultClient Protocol with 14 async methods, ObsidianCLIClient using asyncio subprocess exec, 5 defensive JSON parsers, and 4-class exception hierarchy -- 51 tests all green**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-08T05:13:44Z
- **Completed:** 2026-03-08T05:21:19Z
- **Tasks:** 2
- **Files created:** 8

## Accomplishments
- VaultClient Protocol defines the full async interface (14 methods) that all downstream tool modules will code against
- ObsidianCLIClient implements the Protocol using asyncio.create_subprocess_exec with timeouts, path sanitization, and structured error handling
- 5 parser functions isolate CLI JSON output handling with defensive defaults for unknown output shapes
- 51 tests pass covering protocol conformance, parser edge cases, subprocess mocking, binary detection, and path safety

## Task Commits

Each task was committed atomically (TDD RED-GREEN):

1. **Task 1 RED: Failing tests for protocol, parsers, exceptions** - `2644541` (test)
2. **Task 1 GREEN: Implement VaultClient Protocol, exceptions, parsers** - `53ccc58` (feat)
3. **Task 2 RED: Failing tests for ObsidianCLIClient** - `e2cf21b` (test)
4. **Task 2 GREEN: Implement ObsidianCLIClient** - `6506368` (feat)

**Plan metadata:** TBD (this commit)

## Files Created/Modified
- `src/obsidian_brain/protocol.py` - VaultClient Protocol with 14 async method signatures
- `src/obsidian_brain/cli_client.py` - ObsidianCLIClient implementation with _run/_run_json core, find_cli_binary, path validation
- `src/obsidian_brain/parsers.py` - parse_note_read, parse_file_list, parse_search_results, parse_tags, parse_daily
- `src/obsidian_brain/exceptions.py` - ObsidianCLIError, NoteNotFoundError, CLITimeoutError, CLINotFoundError
- `tests/conftest.py` - Shared fixtures: mock_cli_output helper, sample JSON fixtures for all CLI command types
- `tests/test_protocol.py` - 5 tests: method existence, async check, runtime_checkable, non-conforming rejection, signatures
- `tests/test_parsers.py` - 19 tests: each parser with valid data, missing fields, empty input, JSON string input
- `tests/test_cli_client.py` - 27 tests: binary detection, _run success/error/timeout, all 14 methods, path sanitization, protocol conformance

## Decisions Made
- VaultClient Protocol uses `@runtime_checkable` so `isinstance(client, VaultClient)` works at runtime for conformance checks
- Parsers accept both `dict` and `str` (JSON) inputs via `_ensure_dict`/`_ensure_list` helpers, since exact CLI output format is an open question
- `CLINotFoundError` inherits from `Exception` (not `ObsidianCLIError`) because a missing binary is not a CLI execution failure
- Path sanitization validates null bytes only; shell injection is prevented structurally by list-form `create_subprocess_exec`
- `_split_note_path` uses `PurePosixPath` to separate folder/name for CLI `create` command's separate `name=` and `path=` args

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pytest-asyncio not installed**
- **Found during:** Task 2 GREEN phase (running tests)
- **Issue:** `asyncio_mode = "auto"` config unrecognized, async test functions not collected
- **Fix:** Installed `pytest-asyncio` package (was in pyproject.toml dev deps but not installed)
- **Files modified:** None (runtime dependency install)
- **Verification:** All 27 CLI client tests pass after install
- **Committed in:** N/A (pip install, not a code change)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minor -- missing test dependency, no scope creep.

## Issues Encountered
None beyond the pytest-asyncio install.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- VaultClient Protocol and ObsidianCLIClient are ready for Plan 01-02 (FastMCP server rewrite and tool migration)
- All tool modules can import `VaultClient` and code against the Protocol
- Test fixtures in conftest.py provide mocked subprocess patterns for all future CLI client tests
- Exception hierarchy ready for use in tool error handling

## Self-Check: PASSED

All 8 created files verified on disk. All 4 commit hashes verified in git log.

---
*Phase: 01-cli-migration*
*Completed: 2026-03-08*
