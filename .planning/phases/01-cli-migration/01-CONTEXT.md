# Phase 1: CLI Migration - Context

**Gathered:** 2026-03-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the REST API backend (`httpx` + Obsidian Local REST API plugin) with Obsidian CLI subprocess calls, and migrate from `mcp-use` to the official `mcp` SDK (FastMCP). All existing tools that have CLI equivalents must work identically. Tools without CLI equivalents are removed.

</domain>

<decisions>
## Implementation Decisions

### REST backend fate
- REST backend is deleted entirely after migration — not kept as fallback
- VaultClient Protocol defines the interface (for testability and clean boundaries)
- ObsidianCLIClient implements the Protocol
- Snapshot current REST behavior as integration tests before migration begins — these become the migration contract
- No `OBSIDIAN_BACKEND` env var — CLI is the only backend, no switching needed
- `httpx`, `mcp-use`, and `pytest-httpx` removed from dependencies

### Startup & CLI detection
- Hard error if Obsidian CLI binary not found at startup — server refuses to start
- Also check for running Obsidian instance if CLI requires it (research will determine if this is needed)
- CLI binary located via PATH lookup by default, with `OBSIDIAN_CLI_PATH` env var override
- Error message shows full diagnostic: binary path searched, vault path configured, Obsidian running status, and link to Obsidian 1.8+ download

### Search capability gaps
- Philosophy: CLI is the truth — only expose what CLI natively supports
- DQL (Dataview) and JsonLogic search — drop if CLI doesn't support them
- Text search — only keep if CLI has a native search command (no Python-side reimplementation)
- Periodic notes (daily/weekly/monthly) — same rule, drop if CLI has no native support
- Unsupported tool modules are removed entirely — no stubs, no "not supported" messages

### Docker & documentation cleanup
- Delete Dockerfile and docker-compose.yml — Docker is incompatible with CLI approach
- Update README in this phase — remove Docker section, add CLI requirements (Obsidian 1.8+, CLI on PATH)
- Update SPECIFICATION.md in this phase — rewrite to reflect CLI backend architecture

### Claude's Discretion
- FastMCP server structure (single file vs modular register_*_tools pattern)
- CLI output parsing implementation details
- Cache refresh optimization for CLI (batch vs sequential)
- Subprocess timeout values and retry logic
- How to structure the VaultClient Protocol methods

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `VaultCache` (`cache.py`): In-memory cache with async lock, backlink index, tag index — reusable as-is, just needs a different data source
- Pydantic models (`models.py`): `NoteMetadata`, `VaultStructure`, `NoteContent`, `FileEntry`, etc. — all backend-agnostic, fully reusable
- `utils/frontmatter.py` and `utils/wikilinks.py`: Pure text processing, no REST dependency — fully reusable
- `knowledge.py` and `memory.py`: Higher-level modules that may depend on client — need client swap only

### Established Patterns
- Tool registration: `register_*_tools(server)` functions with `@server.tool()` decorator — pattern needs adaptation for FastMCP
- Client usage: `async with ObsidianClient() as client:` context manager in every tool — will change to CLI client
- Error handling: `NoteNotFoundError` / `ObsidianAPIError` exceptions with JSON error responses — pattern worth preserving
- Cache is a global singleton (`vault_cache`) — no dependency injection currently

### Integration Points
- `main.py`: Currently a stub using `mcp_use.server.MCPServer` — needs full rewrite for FastMCP
- `client.py`: The primary replacement target — 15 methods across directory ops, note CRUD, search, periodic notes
- `tools/__init__.py`: Empty — tool registration happens in individual modules
- `pyproject.toml`: Dependencies and entry point (`obsidian-brain = "obsidian_brain.server:main"`) need updating

</code_context>

<specifics>
## Specific Ideas

- "CLI is the truth" — strong preference for only exposing what CLI natively supports rather than reimplementing missing features in Python
- Clean break philosophy — no backward compatibility shims, no deprecated code, no dual backends
- Snapshot-first migration — capture current behavior before changing anything, use snapshots as the contract

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-cli-migration*
*Context gathered: 2026-03-08*
