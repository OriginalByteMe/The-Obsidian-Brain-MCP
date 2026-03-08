# Requirements: The Obsidian Brain v2

**Defined:** 2026-03-08
**Core Value:** The agent can seamlessly read from and write to your Obsidian vault during any conversation, building a persistent knowledge base that grows smarter over time.

## v1 Requirements

### MCP SDK Migration

- [ ] **SDK-01**: MCP server uses official `mcp` SDK (FastMCP) instead of `mcp-use`
- [ ] **SDK-02**: All existing tool registrations work with FastMCP decorator API
- [ ] **SDK-03**: All existing resource registrations work with FastMCP
- [ ] **SDK-04**: stdio transport works identically to current behavior
- [ ] **SDK-05**: `mcp-use`, `httpx`, and `pytest-httpx` removed from dependencies

### CLI Backend

- [ ] **CLI-01**: `VaultClient` Protocol defines the interface both REST and CLI backends implement
- [ ] **CLI-02**: `ObsidianCLIClient` executes vault operations via Obsidian CLI subprocess calls
- [ ] **CLI-03**: All CLI subprocess calls are async (`asyncio.create_subprocess_exec`)
- [ ] **CLI-04**: CLI output parsing is isolated in dedicated parser module (not in tool handlers)
- [ ] **CLI-05**: All subprocess calls have explicit timeouts (default 30s)
- [ ] **CLI-06**: Note paths are sanitized before CLI invocation (no command injection)
- [ ] **CLI-07**: Environment-based backend selection (`OBSIDIAN_BACKEND=cli|rest`)
- [ ] **CLI-08**: CLI client detects Obsidian CLI binary availability on startup

### Tool Migration

- [ ] **TOOL-01**: All 8 existing tool modules work with CLI backend without logic changes
- [ ] **TOOL-02**: Cache refresh works with CLI backend (batch operations where possible)
- [ ] **TOOL-03**: Cache invalidates specific entries after write operations (not full refresh required)
- [ ] **TOOL-04**: Existing MCP tool response shapes are preserved (backward compatible)
- [ ] **TOOL-05**: Integration tests capture current behavior before migration begins

### New MCP Tools

- [ ] **NEW-01**: Graph traversal tool — find connection paths between two notes via links
- [ ] **NEW-02**: Graph traversal tool — list notes within N link hops of a given note
- [ ] **NEW-03**: Template-based note creation — discover user's templates folder
- [ ] **NEW-04**: Template-based note creation — create notes using Obsidian templates
- [ ] **NEW-05**: Vault analytics — identify orphan notes (no incoming or outgoing links)
- [ ] **NEW-06**: Vault analytics — generate tag summary with counts and hierarchy
- [ ] **NEW-07**: Vault analytics — generate vault structure health overview

### Claude Code Plugin

- [ ] **PLUG-01**: Plugin provides CLAUDE.md with auto-detection rules and vault conventions
- [ ] **PLUG-02**: Plugin registers slash commands for common operations (`/save-memory`, `/vault-search`, `/remember`)
- [ ] **PLUG-03**: Plugin hooks detect noteworthy moments during conversations
- [ ] **PLUG-04**: Plugin asks user permission before any vault write operation
- [ ] **PLUG-05**: Plugin actions are visible in conversation (not silent side effects)
- [ ] **PLUG-06**: Plugin hook failures are reported to the agent (not swallowed)
- [ ] **PLUG-07**: Plugin is independently installable from the MCP server

### Agent Memory

- [ ] **MEM-01**: Agent memories stored in dedicated folder in vault (e.g., `_agent/`)
- [ ] **MEM-02**: Memory taxonomy defined: workflow, fact, preference, session types
- [ ] **MEM-03**: Per-type memory caps with oldest-first eviction
- [ ] **MEM-04**: Tag-based memory retrieval (not "load all memories")
- [ ] **MEM-05**: Vault structure learning — agent maps user's note conventions on first use
- [ ] **MEM-06**: Agent self-memory — stores how to traverse vault, user workflow preferences
- [ ] **MEM-07**: Auto-detection has quality threshold (not every moment is stored)

### Vault Structure Learning

- [ ] **VAULT-01**: Plugin bootstraps by analyzing vault structure and detecting patterns
- [ ] **VAULT-02**: Pattern detection outputs confidence scores, not binary classifications
- [ ] **VAULT-03**: User can correct detected patterns; corrections stored as high-priority memories
- [ ] **VAULT-04**: New notes follow user's detected conventions (frontmatter, naming, folder placement)
- [ ] **VAULT-05**: Notes created in safe namespace until user confirms agent should write to their structure

## v2 Requirements

### Headless Obsidian

- **HEAD-01**: HeadlessManager starts Obsidian without GUI when CLI requires running instance
- **HEAD-02**: PID file tracking prevents duplicate headless instances
- **HEAD-03**: Signal handlers ensure cleanup on process exit (SIGTERM, SIGINT)
- **HEAD-04**: Health check verifies headless process is responsive
- **HEAD-05**: Startup timeout (30s) with kill-and-report on failure

### Agent Skills Storage (Experimental)

- **SKILL-01**: Agent can store reusable skills/scripts as notes in Obsidian
- **SKILL-02**: Agent can search and load skills from vault
- **SKILL-03**: Skills are versioned with frontmatter metadata

### Advanced Memory

- **AMEM-01**: Memory consolidation — agent reviews and merges related memories
- **AMEM-02**: Context injection — relevant memories auto-loaded at session start
- **AMEM-03**: Session summaries — auto-generated at conversation end

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time vault file watching | Adds platform-fragile complexity; manual cache refresh sufficient for v1 |
| Direct filesystem access for writes | Bypasses Obsidian's plugin ecosystem and sync; all writes through CLI |
| Non-Claude-Code client support in plugin | Plugin is Claude Code-specific by design; MCP server remains generic |
| Remote/server headless deployment | Local development tool only; remote adds auth/networking complexity |
| Mobile Obsidian support | CLI is desktop-only |
| Semantic/vector search | Requires embedding infrastructure; massive scope expansion |
| Multi-vault support | Config complexity; single vault per server instance |
| Custom Obsidian plugin (JS/TS) | Second language and build system; use built-in CLI instead |
| Docker deployment for CLI backend | CLI requires local Obsidian; Docker story incompatible with CLI approach |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SDK-01..05 | Phase 1: CLI Migration | Pending |
| CLI-01..08 | Phase 1: CLI Migration | Pending |
| TOOL-01..05 | Phase 1: CLI Migration | Pending |
| NEW-01..07 | Phase 2: New MCP Tools | Pending |
| PLUG-01..07 | Phase 3: Claude Code Plugin | Pending |
| MEM-01..07 | Phase 4: Agent Memory and Vault Learning | Pending |
| VAULT-01..05 | Phase 4: Agent Memory and Vault Learning | Pending |

**Coverage:**
- v1 requirements: 39 total
- Mapped to phases: 39
- Unmapped: 0

---
*Requirements defined: 2026-03-08*
*Last updated: 2026-03-08 after roadmap creation*
