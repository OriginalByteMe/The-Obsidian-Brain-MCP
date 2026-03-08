# The Obsidian Brain v2

## What This Is

A two-part system that turns Obsidian into an always-available brain for AI-assisted development. The MCP server provides programmatic vault access via the official Obsidian CLI (replacing the REST API), while a dedicated Claude Code plugin auto-detects moments worth remembering and creates structured notes — learning your vault conventions and building its own memory along the way.

## Core Value

The agent can seamlessly read from and write to your Obsidian vault during any conversation, building a persistent knowledge base that grows smarter over time.

## Requirements

### Validated

<!-- Shipped and confirmed valuable — existing codebase capabilities. -->

- ✓ MCP server with stdio transport — existing
- ✓ Note CRUD (get, create, edit, delete) via MCP tools — existing
- ✓ Vault search (text search, tag search) — existing
- ✓ In-memory vault cache with manual refresh — existing
- ✓ Backlink index and link graph queries — existing
- ✓ Frontmatter parsing and manipulation — existing
- ✓ Wikilink extraction, injection, and resolution — existing
- ✓ Onboarding flow (vault pattern detection, config generation) — existing
- ✓ Knowledge base management (store/retrieve knowledge entries) — existing
- ✓ Memory management (agent memories stored in vault) — existing
- ✓ Pydantic data models for vault structures — existing
- ✓ Docker deployment support — existing

### Active

<!-- Current scope. Building toward these. -->

- [ ] Replace REST API backend with official Obsidian CLI (1.8+)
- [ ] Headless Obsidian fallback for local CLI availability
- [ ] Graph traversal tools (navigate links, find connection paths between notes)
- [ ] Template-based note creation (use existing Obsidian templates)
- [ ] Vault-wide analytics (orphan notes, tag summaries, structure overview)
- [ ] Claude Code plugin with auto-detection of noteworthy moments
- [ ] Permission-based writing (plugin asks before creating notes)
- [ ] Vault structure learning (plugin bootstraps by mapping user's conventions)
- [ ] Dedicated agent memory folder in vault
- [ ] Structured note creation following user's detected patterns
- [ ] Agent self-memory (how to traverse the vault, user workflow preferences)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Agent skill/script storage in Obsidian — experimental stretch goal, not v1
- Remote/server headless deployment — headless is local-only reliability
- Support for non-Claude-Code clients in plugin — plugin is Claude Code-specific
- Real-time vault file watching — CLI-based, manual cache refresh is sufficient for v1
- Mobile Obsidian support — desktop CLI only

## Context

- Existing Python 3.12+ MCP server built on `mcp-use` framework with `httpx` REST API client
- Currently depends on Obsidian Local REST API plugin (community plugin) — being replaced by official CLI
- Obsidian CLI ships with Obsidian 1.8+ as a built-in feature
- Obsidian headless mode allows running Obsidian without GUI for CLI access
- Claude Code plugins use hooks, slash commands, and CLAUDE.md integration
- Agent memories currently stored in vault under `Obsidian Brain/` folder via YAML-formatted markdown
- Onboarding system already detects vault patterns (PARA, Zettelkasten, etc.)

## Constraints

- **Runtime**: Python 3.12+ — existing codebase, no reason to change
- **CLI dependency**: Obsidian 1.8+ required — users must have recent Obsidian
- **Plugin format**: Must conform to Claude Code plugin conventions (hooks, skills, CLAUDE.md)
- **Vault access**: All vault operations through Obsidian CLI — never direct filesystem access
- **Backward compatibility**: Existing MCP tool interfaces should remain stable for current users

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Replace REST API with Obsidian CLI | CLI is official, built-in — no community plugin dependency | — Pending |
| Headless as local fallback only | User doesn't need remote deployment, just reliability | — Pending |
| Separate Claude Code plugin from MCP | Plugin has different concerns (auto-detection, hooks) vs MCP (vault tools) | — Pending |
| Dedicated agent memory folder | Clean separation between user notes and agent notes | — Pending |
| Permission before writing | User wants to approve notes before they're created | — Pending |

---
*Last updated: 2026-03-08 after initialization*
