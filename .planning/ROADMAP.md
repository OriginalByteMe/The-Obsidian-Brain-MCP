# Roadmap: The Obsidian Brain v2

## Overview

Migrate the existing MCP server from community REST API plugin to official Obsidian CLI, add graph/template/analytics tools, build a Claude Code plugin for auto-detection of noteworthy moments, and give the agent a structured memory system that learns vault conventions. Four phases, each delivering a coherent capability that unblocks the next.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (e.g., 2.1): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: CLI Migration** - Replace REST API and mcp-use with Obsidian CLI backend and official MCP SDK
- [ ] **Phase 2: New MCP Tools** - Add graph traversal, template-based creation, and vault analytics
- [ ] **Phase 3: Claude Code Plugin** - Build behavioral layer for auto-detection, permissions, and slash commands
- [ ] **Phase 4: Agent Memory and Vault Learning** - Structured memory system with taxonomy, caps, and vault convention detection

## Phase Details

### Phase 1: CLI Migration
**Goal**: The MCP server runs on the official MCP SDK and accesses the vault through Obsidian CLI instead of the REST API, with all existing tools working identically
**Depends on**: Nothing (first phase)
**Requirements**: SDK-01, SDK-02, SDK-03, SDK-04, SDK-05, CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, CLI-07, CLI-08, TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05
**Success Criteria** (what must be TRUE):
  1. User can install and run the MCP server with only the `mcp` SDK -- `mcp-use`, `httpx`, and `pytest-httpx` are gone from dependencies
  2. All 8 existing tool modules (vault, links, tags, search, daily, knowledge, onboarding, memory) produce the same response shapes as pre-migration via the CLI backend
  3. REST backend is fully removed -- no client.py, no httpx dependency, no Docker files, no backend-switching env var
  4. CLI operations on a 500-note vault complete cache refresh within a reasonable time (no 10x regression from REST baseline)
  5. Note paths containing special characters (backticks, dollar signs, semicolons) are handled safely without command injection
**Plans:** 5/5 plans executed

Plans:
- [x] 01-00-PLAN.md -- Pre-migration behavior snapshots and response shape contract tests
- [x] 01-01-PLAN.md -- Foundation: VaultClient Protocol, CLI client, parsers, exceptions, test infrastructure
- [x] 01-02-PLAN.md -- Server + Core Tools: FastMCP server rewrite, migrate vault/links/tags/search/daily tools
- [x] 01-03-PLAN.md -- Higher-level Tools: Migrate knowledge/memory/onboarding tools and resources
- [x] 01-04-PLAN.md -- Cache + Cleanup + Docs: Cache migration, delete REST/Docker artifacts, update deps and docs

**Research gaps to resolve before implementation:**
- Obsidian CLI exact subcommands and JSON output support (CRITICAL -- entire migration depends on this)
- Whether CLI works without a running Obsidian instance (determines if headless fallback is needed at all)
- CLI batch operation support (affects cache refresh performance)

---

### Phase 2: New MCP Tools
**Goal**: Users have graph navigation, template-based note creation, and vault health analytics available as MCP tools
**Depends on**: Phase 1
**Requirements**: NEW-01, NEW-02, NEW-03, NEW-04, NEW-05, NEW-06, NEW-07
**Success Criteria** (what must be TRUE):
  1. User can ask "how is note A connected to note B" and get the link path between them
  2. User can ask "what notes are near this note" and get notes within N link hops
  3. User can create a new note from any template in their vault's templates folder
  4. User can get a vault health report showing orphan notes, tag hierarchy with counts, and structure overview
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

---

### Phase 3: Claude Code Plugin
**Goal**: A standalone Claude Code plugin detects noteworthy moments, asks permission before writing, and provides slash commands for vault interaction
**Depends on**: Phase 1 (working MCP server; does not depend on Phase 2)
**Requirements**: PLUG-01, PLUG-02, PLUG-03, PLUG-04, PLUG-05, PLUG-06, PLUG-07
**Success Criteria** (what must be TRUE):
  1. User can install the plugin independently from the MCP server (separate directory, no Python imports)
  2. Plugin provides CLAUDE.md that teaches Claude Code when and how to interact with the vault
  3. User can run `/save-memory`, `/vault-search`, and `/remember` slash commands during any conversation
  4. When the plugin detects a noteworthy moment, it asks the user for permission before writing anything to the vault
  5. All plugin actions (memory suggestions, vault writes, hook outcomes) are visible in the conversation -- no silent side effects
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

**Research gaps to resolve before implementation:**
- Claude Code plugin hook API and event payloads (determines hook architecture)
- Claude Code plugin distribution/packaging format (affects installation story)

---

### Phase 4: Agent Memory and Vault Learning
**Goal**: The agent has a structured memory system with taxonomy and caps, learns the user's vault conventions, and creates notes that follow detected patterns
**Depends on**: Phase 1, Phase 3
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04, MEM-05, MEM-06, MEM-07, VAULT-01, VAULT-02, VAULT-03, VAULT-04, VAULT-05
**Success Criteria** (what must be TRUE):
  1. Agent memories are stored in a dedicated folder (e.g., `_agent/`) separate from user notes, organized by type (workflow, fact, preference, session)
  2. Each memory type has a cap; when exceeded, oldest memories are evicted automatically
  3. User can retrieve memories by tag (e.g., "memories about Python testing") rather than loading all memories
  4. On first use, the plugin analyzes vault structure and reports detected patterns with confidence scores -- user can correct any detection
  5. Notes created by the agent follow the user's detected conventions (frontmatter format, naming, folder placement) or land in a safe namespace until the user confirms
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

---

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4
Note: Phase 3 can begin after Phase 1 (does not require Phase 2).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. CLI Migration | 5/5 | Complete | 2026-03-08 |
| 2. New MCP Tools | 0/2 | Not started | - |
| 3. Claude Code Plugin | 0/2 | Not started | - |
| 4. Agent Memory and Vault Learning | 0/2 | Not started | - |
