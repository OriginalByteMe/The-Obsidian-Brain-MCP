# Codebase Concerns

**Analysis Date:** 2026-03-08

## Tech Debt

**Duplicate `InvalidBacklinkError` class:**
- Issue: The same exception class `InvalidBacklinkError` is defined identically in two files
- Files: `src/obsidian_brain/tools/vault.py` (line 20), `src/obsidian_brain/tools/links.py` (line 19)
- Impact: Maintenance burden; changes to one won't propagate to the other. Neither class is actually raised -- both tools return JSON error responses instead of raising.
- Fix approach: Remove both definitions. Neither is used as an exception (they return JSON error dicts instead). If needed, define once in `src/obsidian_brain/client.py` alongside `ObsidianAPIError`.

**Stale `main.py` example file at project root:**
- Issue: `main.py` contains a demo/example MCP server (`"My Server"`) with toy tools (`echo`, `calculate`, `get_time`) unrelated to the actual project
- Files: `main.py`
- Impact: Confusing for contributors; could be mistaken for the real entry point. The actual entry point is `src/obsidian_brain/server.py` via `obsidian_brain.server:main`.
- Fix approach: Delete `main.py` or rename to `examples/demo_server.py`.

**Inconsistent config path references between docs and code:**
- Issue: Server instructions reference `.obsidian-brain/` folder, but actual code uses `Obsidian Brain/` (non-dot-prefixed) because the REST API does not list hidden folders. Docstrings in `src/obsidian_brain/tools/onboarding.py` (lines 27-29, 65-66) still reference `.obsidian-brain/`.
- Files: `src/obsidian_brain/server.py` (lines 47-55), `src/obsidian_brain/onboarding.py` (lines 20-21), `src/obsidian_brain/tools/onboarding.py` (lines 27, 65)
- Impact: Users and LLMs reading the tool descriptions get misleading path information.
- Fix approach: Update all docstrings and server instructions to reference `Obsidian Brain/` instead of `.obsidian-brain/`.

**New HTTP client created per tool call:**
- Issue: Every tool function creates a fresh `ObsidianClient()` context manager (`async with ObsidianClient() as client:`), which instantiates a new `httpx.AsyncClient` per call. There is no connection pooling or client reuse.
- Files: `src/obsidian_brain/tools/vault.py`, `src/obsidian_brain/tools/memory.py`, `src/obsidian_brain/tools/links.py`, `src/obsidian_brain/tools/daily.py`, `src/obsidian_brain/tools/search.py`, `src/obsidian_brain/tools/tags.py`, `src/obsidian_brain/tools/onboarding.py`
- Impact: Increased latency for every tool call due to connection setup overhead. SSL handshake repeated each time.
- Fix approach: Create a shared client singleton (similar to `vault_cache`) or a factory that reuses the underlying `httpx.AsyncClient`. Manage lifecycle at server level.

**Global singleton pattern overuse:**
- Issue: Three global singletons (`vault_cache`, `memory_manager`, `onboarding_manager`) are created at module import time. This makes testing difficult and couples modules tightly.
- Files: `src/obsidian_brain/cache.py` (line 351), `src/obsidian_brain/memory.py` (line 212), `src/obsidian_brain/onboarding.py` (line 540)
- Impact: Cannot inject dependencies for testing. Cannot run multiple server instances with different configurations.
- Fix approach: Use dependency injection via the server instance or a service container. Pass instances explicitly rather than importing globals.

## Known Bugs

**`edit_memory` passes original content as "existing" to `update_memory_content`:**
- Symptoms: When editing a memory, the `update_memory_content` method receives the raw file content as `existing_content`, but `new_content` is the result of search-replace on that same raw content. The method then tries to parse `existing_content` as if it has frontmatter, but the content from `get_note` may already have frontmatter stripped by the API.
- Files: `src/obsidian_brain/tools/memory.py` (lines 252-278)
- Trigger: Edit a memory that has frontmatter -- the frontmatter parsing in `update_memory_content` may double-process or lose metadata depending on the API response format.
- Workaround: None known; may work in practice if the API returns raw content with frontmatter intact.

**`check_onboarding_status` checks for wrong path prefix:**
- Symptoms: The function checks `f.startswith(".obsidian-brain/")` (line 78 of `src/obsidian_brain/onboarding.py`) but the actual config path is `"Obsidian Brain/config.yml"` (line 20). The `has_config` check on line 78 will never be True.
- Files: `src/obsidian_brain/onboarding.py` (lines 78-79)
- Trigger: Call `check_onboarding_status` -- the `partial: True` state (lines 88-95) is unreachable.
- Workaround: The `config_exists` check on line 79 works correctly, so the main flow (onboarded vs not) functions, but the partial detection is broken.

**`_resolve_link_to_path` rebuilds lookup map on every call:**
- Symptoms: Performance degradation during link graph traversal
- Files: `src/obsidian_brain/tools/links.py` (lines 260-303)
- Trigger: Call `get_linked_notes` with depth > 1. Each BFS step calls `_resolve_link_to_path` which iterates all notes to build a lookup map, then discards it.
- Workaround: For small vaults this is negligible. For large vaults (1000+ notes) with depth 3 traversal, expect significant slowdown.

## Security Considerations

**SSL verification disabled by default:**
- Risk: Man-in-the-middle attacks when connecting to Obsidian REST API over HTTPS
- Files: `src/obsidian_brain/client.py` (lines 79-80)
- Current mitigation: Default is `verify_ssl=False`. The `OBSIDIAN_VERIFY_SSL` env var defaults to `"false"`.
- Recommendations: For local-only usage (127.0.0.1) this is acceptable. When `OBSIDIAN_URL` is set to a remote host, warn or default to `verify_ssl=True`. Document the risk for remote configurations.

**API key read from environment with empty fallback:**
- Risk: Server starts and makes unauthenticated requests if `OBSIDIAN_API_KEY` is not set, with an empty bearer token
- Files: `src/obsidian_brain/client.py` (line 63)
- Current mitigation: None -- empty string is used as bearer token
- Recommendations: Validate that `api_key` is non-empty at client init time and raise a clear configuration error.

**Regex injection in `edit_memory` tool:**
- Risk: When `mode="regex"`, user-supplied patterns are compiled directly with `re.compile(search, re.DOTALL | re.MULTILINE)`. Malicious or malformed patterns could cause ReDoS (Regular Expression Denial of Service).
- Files: `src/obsidian_brain/tools/memory.py` (lines 255-258)
- Current mitigation: Catches `re.error` but no timeout or complexity limits.
- Recommendations: Add a timeout or use a regex engine with backtracking limits. Since this is LLM-driven, risk is low but worth documenting.

**No path traversal protection:**
- Risk: Tool functions accept arbitrary paths (e.g., `create_note("../../etc/passwd", content)`). The Obsidian REST API likely sandboxes to the vault, but no client-side validation exists.
- Files: `src/obsidian_brain/client.py` (all path-accepting methods)
- Current mitigation: Relies entirely on the Obsidian REST API to reject invalid paths.
- Recommendations: Add client-side path validation to reject `..` traversal and absolute paths.

## Performance Bottlenecks

**Sequential per-note API calls during cache refresh:**
- Problem: `VaultCache.refresh()` fetches metadata for every markdown file one-at-a-time in a serial loop
- Files: `src/obsidian_brain/cache.py` (lines 170-193)
- Cause: `for file_path in md_files: ... await client.get_note(...)` -- each note is fetched sequentially
- Improvement path: Use `asyncio.gather()` with a concurrency limiter (e.g., `asyncio.Semaphore(10)`) to fetch notes in parallel batches. For a vault with 500 notes, this could reduce refresh time from minutes to seconds.

**Sequential recursive directory listing:**
- Problem: `_get_directory_tree` recurses into subdirectories one-at-a-time
- Files: `src/obsidian_brain/cache.py` (lines 228-265)
- Cause: Each subdirectory listing requires a separate API call, awaited sequentially
- Improvement path: Same as above -- use `asyncio.gather()` for parallel directory listing. Alternatively, check if the Obsidian REST API supports recursive listing in a single call.

**Linear scan for note metadata lookup:**
- Problem: `get_note_metadata()` iterates all notes to find one by path
- Files: `src/obsidian_brain/cache.py` (lines 89-105)
- Cause: Notes stored as a flat list, not indexed by path
- Improvement path: Add a `dict[str, NoteMetadata]` index (keyed by path) alongside the notes list. Build it during `_build_structure`.

**`list_memories` fetches all vault files then filters:**
- Problem: Calls `client.get_all_files("/")` (full recursive listing of entire vault) just to find memory files in one directory
- Files: `src/obsidian_brain/tools/memory.py` (lines 40-41)
- Cause: No targeted directory listing for just the memories path
- Improvement path: Call `client.list_directory("Obsidian Brain/memories")` instead of scanning the entire vault.

## Fragile Areas

**Frontmatter round-tripping:**
- Files: `src/obsidian_brain/utils/frontmatter.py`, `src/obsidian_brain/memory.py`
- Why fragile: Two independent frontmatter parsing implementations exist -- `python-frontmatter` library in `utils/frontmatter.py` and manual `---` splitting with `yaml.safe_load` in `memory.py` (lines 90-97). These can produce different results for edge cases (e.g., content containing `---` separators).
- Safe modification: Use `python-frontmatter` consistently everywhere. Replace the manual parsing in `memory.py`.
- Test coverage: No tests exist for either implementation.

**Wikilink resolution logic duplicated:**
- Files: `src/obsidian_brain/cache.py` (lines 286-347), `src/obsidian_brain/tools/links.py` (lines 260-303), `src/obsidian_brain/utils/wikilinks.py` (lines 141-211)
- Why fragile: Three separate implementations of wikilink-to-path resolution with slightly different matching logic. Changes to one do not propagate to others.
- Safe modification: Consolidate into a single `resolve_wikilink` function in `src/obsidian_brain/utils/wikilinks.py` and call it from cache and links modules.
- Test coverage: No tests.

**Cache dependency without automatic invalidation:**
- Files: `src/obsidian_brain/cache.py`
- Why fragile: Multiple tools (backlinks, tags, link graph) depend on cached data. Any vault modification through tools (create/update/delete note, add/remove tags) does NOT invalidate or update the cache. Users must manually call `refresh_vault_structure` to sync.
- Safe modification: After any write operation, either invalidate the cache or perform targeted updates (e.g., update a single note's metadata in the cache).
- Test coverage: No tests for cache behavior.

## Scaling Limits

**In-memory vault cache:**
- Current capacity: Stores all note metadata (path, title, tags, links, frontmatter) for every note in memory
- Limit: For vaults with 10,000+ notes, the `VaultStructure` Pydantic model and backlink index will consume significant memory. The `model_dump_json()` call for the `vault://structure` resource serializes everything at once.
- Scaling path: Implement lazy loading, pagination for resources, or on-disk caching with SQLite.

**Full vault scan for onboarding status check:**
- Current capacity: `check_onboarding_status` calls `get_all_files("/")` which recursively lists the entire vault
- Limit: For large vaults this is unnecessarily expensive just to check if one config file exists
- Scaling path: Use `client.note_exists("Obsidian Brain/config.yml")` instead of listing all files.

## Dependencies at Risk

**`mcp-use` library:**
- Risk: Version pinned to `>=1.5.1` (floor only). This is the core MCP framework the server depends on. Breaking changes in the API (e.g., `MCPServer` constructor, `@server.tool()` decorator, `@server.resource()` decorator) would break the entire server.
- Impact: All tool registration and server lifecycle depends on this library
- Migration plan: Pin to a specific version range (e.g., `>=1.5.1,<2.0.0`). Monitor releases for breaking changes.

## Missing Critical Features

**No test suite:**
- Problem: The `tests/` directory contains only `__init__.py`. No test files exist despite `pytest`, `pytest-asyncio`, and `pytest-httpx` being listed as dev dependencies. Old `__pycache__` files reference deleted test modules (`test_resources`, `test_search`, `test_session_tools`, `test_hooks`).
- Blocks: Cannot verify correctness of any component. Refactoring (especially the duplicated wikilink resolution and frontmatter parsing) is risky without tests.

**No input validation on note paths:**
- Problem: Note paths are passed directly to the API without validation for format, length, or allowed characters
- Blocks: Cannot prevent creation of notes with problematic names (e.g., names with special characters that break on certain filesystems)

**No rate limiting or retry logic:**
- Problem: API calls have a 30-second timeout but no retry on transient failures (network blips, API temporarily unavailable)
- Blocks: Reliability in environments where Obsidian app may be restarting or temporarily unresponsive

**No lock file committed:**
- Problem: Neither `uv.lock` nor any other lock file is committed to the repository. The `.gitignore` has `uv.lock` commented out but not actively ignored -- it simply does not exist.
- Blocks: Reproducible builds. The `Dockerfile` tries `uv sync --frozen` first (which requires a lockfile) and falls back to `uv sync --no-dev`.

## Test Coverage Gaps

**Entire codebase is untested:**
- What's not tested: All modules -- client, cache, memory, onboarding, knowledge, all tools, all utilities
- Files: Every file in `src/obsidian_brain/`
- Risk: Any change could introduce regressions undetected. The duplicated logic (wikilink resolution, frontmatter parsing) is especially vulnerable.
- Priority: High -- start with `src/obsidian_brain/utils/wikilinks.py` and `src/obsidian_brain/utils/frontmatter.py` (pure functions, easy to test), then `src/obsidian_brain/cache.py` (core logic), then tool modules (using `pytest-httpx` for mocking).

---

*Concerns audit: 2026-03-08*
