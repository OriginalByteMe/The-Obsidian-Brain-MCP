---
phase: 01-cli-migration
verified: 2026-03-08T06:00:18Z
status: gaps_found
score: 32/35 must-haves verified
gaps:
  - truth: "Tool response shapes are identical to pre-migration format"
    status: partial
    reason: "Shape-contract suites are stale after FastMCP/VaultClient migration and currently fail before asserting shape compatibility."
    artifacts:
      - path: "tests/test_response_shapes.py"
        issue: "Registers tools with old 1-arg signature (register_vault_tools(server)); migrated code requires (server, client)."
      - path: "tests/test_tools_core.py"
        issue: "Assumes old FastMCP call_tool content shape (`result[0].text`) and fails with current return structure."
  - truth: "Snapshot tests form the migration contract -- post-migration tools must produce identical shapes"
    status: partial
    reason: "Snapshots exist, but contract execution is currently blocked by stale harness assumptions; backward-compatibility is not fully proven by passing tests."
---

# Phase 01 Verification Report

## Goal Verdict

**Phase goal:** "The MCP server runs on the official MCP SDK and accesses the vault through Obsidian CLI instead of the REST API, with all existing tools working identically"

**Verdict:** `partially_achieved`

- SDK + CLI migration is implemented and wired correctly in current code.
- Prior wiring blockers from earlier verification are fixed (`register_onboarding_tools(mcp, client)` and `register_knowledge_resource(mcp, client)`).
- Remaining verification gap: response-contract/core shape test harness is stale, so "working identically" is not fully proven by automated tests yet.

## Requirement ID Cross-Reference (PLAN -> REQUIREMENTS)

- Requirement IDs found in phase plan frontmatter: `SDK-01..SDK-05`, `CLI-01..CLI-08`, `TOOL-01..TOOL-05` (18 unique IDs).
- Cross-check against `.planning/REQUIREMENTS.md`: **18/18 accounted for**.
- Missing IDs from REQUIREMENTS: **none**.

## Must-Have Audit

### 01-00-PLAN

| Truth | Status | Evidence |
|---|---|---|
| Current REST API tool responses are captured as snapshot fixtures before any migration code runs | VERIFIED | `tests/test_snapshots.py` exists (frozen shape fixtures) |
| Response shape assertions exist for all kept tools (vault, links, tags, search, daily, knowledge, memory, onboarding) | VERIFIED | `tests/test_response_shapes.py` exists and covers kept modules |
| Snapshot tests form the migration contract -- post-migration tools must produce identical shapes | PARTIAL | Contract suite exists but currently fails before shape checks due stale registration/call assumptions |

### 01-01-PLAN

| Truth | Status | Evidence |
|---|---|---|
| VaultClient Protocol defines the async interface with all methods that have CLI equivalents | VERIFIED | `src/obsidian_brain/protocol.py` lines 11-169 (`VaultClient`, 14 async methods) |
| ObsidianCLIClient implements VaultClient Protocol using asyncio.create_subprocess_exec | VERIFIED | `src/obsidian_brain/cli_client.py` line 136 (`create_subprocess_exec`) |
| All subprocess calls have explicit timeouts via asyncio.wait_for | VERIFIED | `src/obsidian_brain/cli_client.py` line 143 (`asyncio.wait_for`) |
| CLI binary is located via shutil.which with OBSIDIAN_CLI_PATH env var override | VERIFIED | `src/obsidian_brain/cli_client.py` lines 45, 52 |
| Note paths are safe from command injection (list-form exec, no shell=True) | VERIFIED | list-form exec in `_run`; `_validate_path` at line 59; no `shell=True` usage |
| CLI JSON output is parsed in a dedicated parsers module, not inline | VERIFIED | `src/obsidian_brain/parsers.py`; imported in `cli_client.py` |
| Shared exceptions (CLIError, NoteNotFoundError) are in a dedicated module | VERIFIED | `src/obsidian_brain/exceptions.py` |

### 01-02-PLAN

| Truth | Status | Evidence |
|---|---|---|
| MCP server initializes with FastMCP and registers all tools and resources | VERIFIED | `src/obsidian_brain/server.py` lines 8, 23, 136-149 |
| Server runs via mcp.run() on stdio transport | VERIFIED | `src/obsidian_brain/server.py` line 154 |
| All 6 core tool modules accept VaultClient instead of creating ObsidianClient | VERIFIED | `register_*_tools(..., client: VaultClient)` signatures in core tool modules |
| Tool response shapes are identical to pre-migration format | PARTIAL | Not fully proven due failing/stale contract harness (`tests/test_response_shapes.py`) |
| search_advanced and search_jsonlogic tools are removed | VERIFIED | absent from runtime tool registration; removal assertions present in tests |
| get_periodic_note tool is removed; only daily note tools remain | VERIFIED | daily module exposes `get_daily_note`, `append_to_daily`, `create_daily_entry` only |
| No import of mcp_use anywhere in the codebase | VERIFIED | `rg` over `src` found no matches |

### 01-03-PLAN

| Truth | Status | Evidence |
|---|---|---|
| Knowledge, memory, and onboarding tool modules accept VaultClient instead of creating ObsidianClient | VERIFIED | `register_knowledge_tools`, `register_memory_tools`, `register_onboarding_tools` use `client: VaultClient` |
| Higher-level managers (knowledge.py, memory.py, onboarding.py) use VaultClient | VERIFIED | constructors typed to `VaultClient` |
| Resource modules work with FastMCP decorator API | VERIFIED | `@server.resource(...)` in `resources/structure.py` and `resources/knowledge.py` |
| Cache invalidates specific entries after write operations in memory/knowledge tools | VERIFIED | `vault_cache.invalidate_path(...)` in `tools/memory.py` lines 174, 211, 288 |
| All tool response shapes preserved from pre-migration | PARTIAL | Same blocking issue as above: contract suite stale |

### 01-04-PLAN

| Truth | Status | Evidence |
|---|---|---|
| Cache refresh uses VaultClient instead of ObsidianClient | VERIFIED | `src/obsidian_brain/cache.py` line 163 (`refresh(self, client: "VaultClient")`) |
| pyproject.toml depends on mcp>=1.26.0, NOT mcp-use or httpx | VERIFIED | `pyproject.toml` line 21 (`mcp>=1.26.0`), no `mcp-use`/`httpx` |
| pytest-httpx removed from dev dependencies | VERIFIED | not present in `pyproject.toml` |
| Dockerfile and docker-compose.yml are deleted | VERIFIED | both files absent from repo root |
| Old client.py (REST) is deleted | VERIFIED | `src/obsidian_brain/client.py` absent |
| README documents CLI requirements (Obsidian 1.12+, CLI on PATH) | VERIFIED | `README.md` lines 154-158, 332-334 |
| SPECIFICATION.md reflects CLI backend architecture | VERIFIED | `SPECIFICATION.md` lines 21, 69, 210, 252 |
| No import of httpx, mcp_use, or pytest_httpx anywhere in codebase | VERIFIED | no matches in `src` + `pyproject.toml` |
| ROADMAP Phase 1 success criteria align with CLI-only locked decision (no backend-switching language) | VERIFIED | `.planning/ROADMAP.md` line 27 |
| Cache CLI integration tests verify refresh with mocked VaultClient | VERIFIED | `tests/test_cache_cli.py` passes |

### 01-05-PLAN

| Truth | Status | Evidence |
|---|---|---|
| register_onboarding_tools is called with both mcp and client arguments | VERIFIED | `src/obsidian_brain/server.py` line 144 |
| register_knowledge_resource is called with both mcp and client arguments | VERIFIED | `src/obsidian_brain/server.py` line 149 |
| All tool and resource registration calls in server.py pass the client singleton | VERIFIED | all tool/resource registrations validated; `register_structure_resource(mcp)` is correctly cache-only |

## Requirement Status (Phase IDs)

| Requirement | Status | Evidence |
|---|---|---|
| SDK-01 | SATISFIED | FastMCP server import/init in `server.py` |
| SDK-02 | SATISFIED | tool registration via FastMCP decorators in all modules |
| SDK-03 | SATISFIED | resources registered via FastMCP; knowledge resource wiring fixed |
| SDK-04 | SATISFIED | `mcp.run()` in server entrypoint |
| SDK-05 | SATISFIED | `mcp-use/httpx/pytest-httpx` removed |
| CLI-01 | SATISFIED | `VaultClient` protocol implemented |
| CLI-02 | SATISFIED | `ObsidianCLIClient` subprocess backend |
| CLI-03 | SATISFIED | async subprocess operations |
| CLI-04 | SATISFIED | dedicated parser module |
| CLI-05 | SATISFIED | explicit wait_for timeout |
| CLI-06 | SATISFIED | path validation + no shell exec |
| CLI-07 | SATISFIED (CLI-only interpretation) | backend-switching removed by locked CLI-only decision |
| CLI-08 | SATISFIED | startup CLI binary detection (`find_cli_binary`) |
| TOOL-01 | SATISFIED (runtime wiring) | all 8 modules wired in server with client argument |
| TOOL-02 | SATISFIED | cache refresh + tests |
| TOOL-03 | SATISFIED | targeted cache invalidation on writes |
| TOOL-04 | PARTIAL | contract harness stale; shape compatibility not fully proven by green tests |
| TOOL-05 | SATISFIED (artifacts exist) | snapshot/shape contract suites present |

## Test Evidence

### Passing suites (phase-critical backend migration checks)

Command:

```bash
pytest -q tests/test_server.py tests/test_dependencies.py tests/test_protocol.py tests/test_cli_client.py tests/test_parsers.py tests/test_tools_higher.py tests/test_cache_cli.py
```

Result: **110 passed**

### Failing suites (verification gap)

Command:

```bash
pytest -q tests/test_tools_core.py tests/test_response_shapes.py
```

Result: **9 failed, 32 errors, 6 passed**

Primary causes:
- `tests/test_response_shapes.py` still registers tools with pre-migration signatures (`register_*_tools(server)` instead of `(server, client)`).
- `tests/test_tools_core.py` assertions expect older `call_tool` response item shape (`result[0].text`) and no longer match returned structure.

## Final Assessment

Phase 01 implementation is materially complete for SDK/CLI migration and no longer has the earlier server wiring blockers. However, the goal clause "all existing tools working identically" remains **not fully verified** until the contract/core test harness is updated and passing against current FastMCP+VaultClient interfaces.

