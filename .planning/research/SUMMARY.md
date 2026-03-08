# Research Summary

**Project:** The Obsidian Brain v2
**Synthesized:** 2026-03-08

## Key Findings

### 1. CLI Migration Is Clean but Risky

The existing `ObsidianClient` (httpx REST wrapper) is the **only** component touching the REST API. Every tool handler uses `async with ObsidianClient() as client:` — meaning a clean interface swap is possible. However:

- **Obsidian CLI exact capabilities are LOW confidence** — training data only. The CLI may not support structured JSON output, which would make parsing fragile.
- **Performance regression is near-certain** without batch operations — subprocess spawn overhead (~200-500ms) multiplied by N notes during cache refresh could turn seconds into minutes.
- **A spike to validate CLI capabilities is mandatory** before committing to the architecture.

### 2. Stack Simplifies Dramatically

| Change | Impact |
|--------|--------|
| `mcp-use` → `mcp` (FastMCP) | Drop ~40 transitive deps (langchain, posthog, etc.). One-line import change per file. |
| `httpx` → `asyncio.subprocess` | No new deps. Drop httpx + pytest-httpx. |
| Claude Code plugin | Shell scripts + markdown. No Python needed. |
| **Net result** | 4 direct deps → 3 direct deps. ~60 transitive → ~20 transitive. |

### 3. Plugin Is Behavioral, Not Capability

The Claude Code plugin and MCP server have fundamentally different roles:
- **MCP Server** = capability layer (HOW to interact with vault)
- **Plugin** = behavioral layer (WHEN and WHAT to remember)

The plugin should never access the vault directly. It instructs Claude Code to call MCP tools. This maintains a single access path and cache consistency.

### 4. Memory System Needs Design Before Auto-Detection

The current `MemoryManager` has no search, filtering, or eviction. Adding "auto-detection of noteworthy moments" without a memory taxonomy, caps, and relevance filtering will create a junk drawer within weeks.

**Must exist before auto-detection:**
- Memory taxonomy (workflow, fact, preference, session)
- Per-type caps with eviction
- Tag-based retrieval filtering
- Quality threshold for auto-detection

### 5. Headless Mode Is Higher Risk Than Expected

Obsidian is Electron — headless means managing a full Chromium process tree. Zombie processes, vault locks, GPU subprocesses. Should be:
- **Optional and independently disableable**
- **Built last** — it's a fallback, not a prerequisite
- **May be unnecessary** if CLI works without a running Obsidian instance

## Consensus Across Research

All 4 researchers agree on:

1. **CLI backend must come first** — everything depends on it
2. **CLI spike/validation is prerequisite** — verify capabilities before building
3. **Plugin is separate from MCP server** — different runtime, different concerns
4. **Headless is last and optional** — highest risk, lowest priority
5. **Backward compatibility matters** — keep REST backend during migration

## Conflicts and Resolutions

| Conflict | Resolution |
|----------|------------|
| Architecture says "interface-preserving replacement"; Pitfalls says "don't try drop-in" | **Resolution:** Define a `VaultClient` Protocol that both backends implement, but design it with batch operations the REST client lacked. Not a naive drop-in, but a shared interface. |
| Stack says "no new deps needed"; Pitfalls suggests `ruamel.yaml` and `watchdog` | **Resolution:** Defer both. stdlib is sufficient for v1. Add ruamel.yaml only if YAML round-trip issues surface. |
| Features lists "headless management" as differentiator; Pitfalls flags it as highest risk | **Resolution:** Build headless as optional last phase. Start with "tell user to open Obsidian" error message. |

## Critical Research Gaps

These unknowns **must** be resolved during phase-specific research before implementation:

| Gap | Risk | When to Resolve |
|-----|------|-----------------|
| Obsidian CLI exact subcommands and JSON output support | **CRITICAL** — entire migration depends on this | Phase 1 research spike |
| Whether CLI works without running Obsidian instance | **HIGH** — determines if headless is needed at all | Phase 1 research spike |
| Claude Code plugin hook API and event payloads | **HIGH** — determines plugin architecture | Plugin phase research |
| Claude Code plugin distribution/packaging format | **MEDIUM** — affects how users install | Plugin phase research |

## Recommended Phase Structure

Based on all research, the build order should be:

1. **MCP SDK Migration + CLI Spike** — Swap mcp-use for FastMCP (low risk, high value). Validate Obsidian CLI capabilities. This is the foundation.
2. **CLI Backend + Tool Migration** — Build `ObsidianCLIClient` with `VaultClient` Protocol. Migrate tool handlers. Keep REST as fallback.
3. **New MCP Tools** — Graph traversal, template-based creation, vault analytics. Build on working CLI backend.
4. **Claude Code Plugin** — CLAUDE.md, hooks, slash commands. Depends on working MCP server.
5. **Agent Memory System** — Memory taxonomy, auto-detection, vault structure learning. Depends on both plugin and MCP server.
6. **Headless Fallback** — Optional process management. Last because highest risk, lowest priority.

## Confidence Summary

| Area | Confidence | Source |
|------|-----------|--------|
| Existing codebase analysis | HIGH | Direct inspection |
| MCP SDK migration path | HIGH | Verified locally |
| CLI subprocess patterns | HIGH | Well-established Python |
| Obsidian CLI 1.8+ capabilities | LOW | Training data only |
| Claude Code plugin conventions | MEDIUM | Training data |
| Memory system design patterns | MEDIUM | Training data |
| Headless Obsidian behavior | LOW | Training data only |

---
*Synthesis: 2026-03-08*
