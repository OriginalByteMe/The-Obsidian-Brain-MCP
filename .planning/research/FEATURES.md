# Feature Landscape

**Domain:** Obsidian CLI MCP server + Claude Code plugin for AI-agent vault memory
**Researched:** 2026-03-08
**Overall Confidence:** MEDIUM (training data only -- no web search/fetch available)

## Table Stakes

Features users expect. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Note CRUD via Obsidian CLI | Core vault interaction -- users replacing REST API expect feature parity | Medium | Already exists via REST; must replicate with CLI subprocess calls. CLI uses `obsidian://` URI actions or direct `obsidian` binary invocation |
| Full-text vault search | Existing capability users depend on; cannot regress | Medium | CLI may not expose search directly -- may need to fall back to filesystem grep or maintain the search index in-cache |
| Tag read/write in frontmatter | Existing capability; tags are fundamental to Obsidian workflows | Low | Already implemented; just needs backend swap from REST to CLI |
| Backlink index and queries | Existing capability; backlinks are Obsidian's core value proposition | Medium | Requires reading note content and building the link graph -- may need filesystem access if CLI doesn't support this |
| Vault structure cache | Existing capability; performance depends on it | Medium | Same pattern, different data source |
| Memory persistence across sessions | Core value prop of the product -- agent remembers across conversations | Low | Already implemented; storage mechanism (files in vault) stays the same |
| Onboarding / vault pattern detection | Existing capability; reduces setup friction | Low | Already implemented; input source changes but analysis logic is pure |
| Graceful fallback when Obsidian is closed | Users will not always have Obsidian running; CLI operations should degrade gracefully | Medium | Headless mode or direct filesystem access as fallback. Critical for reliability |
| Claude Code MCP server registration | Users must be able to add this as an MCP server in Claude Code config | Low | Already works; just needs updated config examples for CLI backend |
| Permission-based writing | PROJECT.md lists this as active requirement; users want approval before agent writes | Medium | Agent proposes note, user confirms. Aligns with Claude Code's permission model |
| Daily/periodic note operations | Existing capability; daily notes are a core Obsidian workflow | Low | Already implemented; backend swap only |

## Differentiators

Features that set product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Claude Code plugin with auto-detection | Agent automatically recognizes "noteworthy moments" (decisions, learnings, errors) and offers to save them | High | Requires Claude Code plugin hooks (PreToolUse, PostToolUse, Notification hooks) to intercept conversation flow. This is the product's unique value |
| Vault structure learning | Plugin bootstraps by mapping user's conventions (PARA, Zettelkasten, etc.) and follows them | Medium | Already partially implemented in onboarding; plugin layer would invoke this automatically on first use |
| Agent self-memory | Agent stores its own notes about how to traverse the vault, user preferences, workflow patterns | Medium | Goes beyond simple memory CRUD -- agent builds a model of user's vault over time. Stored in dedicated agent folder |
| Graph traversal tools | Navigate links, find connection paths between notes, discover clusters | High | Path-finding (BFS/DFS between two notes), cluster detection, "related notes" suggestions. Partially exists (depth-limited traversal) |
| Template-based note creation | Use existing Obsidian templates when creating notes | Medium | Must discover user's templates folder, parse template variables, apply them. Obsidian Templater syntax is complex |
| Vault-wide analytics | Orphan notes, tag summaries, structure health overview | Low | Partially exists in knowledge base; needs better surfacing as actionable insights |
| Structured note creation following user patterns | Agent creates notes that look like the user wrote them (matching frontmatter, naming, folder placement) | Medium | Onboarding detects patterns; this feature applies them during creation. Requires conventions memory to be consulted on every create |
| Slash commands for common operations | `/save-decision`, `/vault-search`, `/remember` etc. in Claude Code | Medium | Claude Code plugins can register slash commands. Provides quick access to common vault operations without full tool invocation |
| Context injection via CLAUDE.md | Plugin auto-generates project-specific CLAUDE.md with relevant vault context | Medium | On session start, plugin reads vault memories and injects relevant context into the conversation via CLAUDE.md or similar mechanism |
| Headless Obsidian management | Automatically start/stop headless Obsidian when needed for CLI access | High | Process management, health checks, startup timeouts. Only needed when GUI Obsidian is not running |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Real-time file watching / live sync | Adds complexity for marginal value; CLI-based manual refresh is sufficient for v1. File watchers are fragile across platforms | Manual cache refresh on demand. Revisit if users report stale data as a pain point |
| Direct filesystem access for vault operations | Bypasses Obsidian's plugin ecosystem, indexing, and sync. Could corrupt vault state or conflict with Obsidian's own file handling | Always go through Obsidian CLI or (fallback) read-only filesystem access only |
| Support for non-Claude-Code clients in plugin | Plugin is Claude Code-specific by design. Supporting other LLM clients fragments the codebase | Keep MCP server generic (works with any MCP client). Plugin layer is Claude Code only |
| Remote/server headless deployment | Project scope is local development tool. Remote adds auth, networking, security complexity with no clear user need | Headless is local-only for reliability when Obsidian GUI is closed |
| Mobile Obsidian support | CLI is desktop-only. Mobile Obsidian has different APIs and constraints | Desktop CLI only. Mobile users can access vault via Obsidian's own sync |
| Agent skill/script storage | Storing executable scripts in Obsidian is a security concern and out of scope for knowledge management | Store knowledge and memories only. Scripts belong in code repos |
| Custom Obsidian plugin development | Building an Obsidian plugin (JS/TS) to complement the MCP server adds a second language, second build system, second distribution channel | Use Obsidian's built-in CLI and existing plugin ecosystem (Templater, Dataview) |
| Semantic/vector search | Requires embedding infrastructure, vector DB, model hosting. Massive scope expansion | Use Obsidian's built-in text search and link graph for discovery. Semantic search is a separate product |
| Multi-vault support | Adds configuration complexity; most users have one primary vault | Single vault per server instance. Users can run multiple instances if needed |
| Obsidian Sync integration | Proprietary protocol, no public API, would break if Obsidian changes it | Rely on filesystem -- if user has Obsidian Sync, files are already local |

## Feature Dependencies

```
Obsidian CLI backend -----> All vault operations (CRUD, search, tags, links)
                    \
                     +---> Headless Obsidian fallback (needs CLI to work first)

Vault structure cache -----> Backlink index
                     \----> Graph traversal tools
                      \---> Vault-wide analytics
                       \--> Template discovery

Onboarding/pattern detection -----> Structured note creation
                              \---> Agent self-memory (needs to know vault layout)
                               \--> Conventions memory

Memory persistence -----> Agent self-memory (builds on basic memory CRUD)
                    \---> Context injection via CLAUDE.md

Claude Code plugin hooks -----> Auto-detection of noteworthy moments
                          \---> Slash commands
                           \--> Permission-based writing
                            \-> Context injection via CLAUDE.md

Permission-based writing -----> Auto-detection (must ask before saving)
```

## MVP Recommendation

Prioritize:
1. **Obsidian CLI backend** -- foundation for everything; replaces REST API dependency
2. **Graceful fallback** -- headless or read-only filesystem when Obsidian is closed
3. **Permission-based writing** -- table stakes for trust; agent must ask before modifying vault
4. **Claude Code plugin skeleton** -- register hooks, slash commands, CLAUDE.md integration
5. **Auto-detection of noteworthy moments** -- the core differentiator; without this, it's just another MCP server

Defer:
- **Graph traversal tools** -- partially exists; enhance after core migration is stable
- **Template-based note creation** -- nice-to-have; users can use existing Templater plugin
- **Vault-wide analytics** -- partially exists in knowledge base; polish later
- **Headless Obsidian management** -- complex process management; start with "tell user to open Obsidian" fallback
- **Slash commands** -- can add incrementally after plugin skeleton works

## Feature Details by Domain

### Obsidian CLI Operations (MEDIUM confidence -- training data only)

The Obsidian CLI (1.8+) provides vault operations through the `obsidian` binary. Based on training data, expected capabilities include:

- **Open vault**: `obsidian --vault <path>`
- **Open note**: `obsidian://open?vault=name&file=path`
- **Create note**: `obsidian://new?vault=name&file=path&content=...`
- **Search**: `obsidian://search?vault=name&query=...`
- **URI protocol actions**: Various `obsidian://` protocol handlers

**Confidence note:** The exact CLI subcommands and their capabilities need verification against official Obsidian 1.8+ documentation. The CLI may be more limited than the REST API for programmatic operations (especially bulk reads, search results, metadata queries). Research flag: verify CLI capabilities before implementation.

### Claude Code Plugin Hooks (MEDIUM confidence -- training data only)

Claude Code plugins can integrate via:

- **Hooks**: `PreToolUse`, `PostToolUse`, `Notification`, `Stop` -- intercept agent lifecycle events
- **Slash commands**: Custom `/commands` registered by the plugin
- **CLAUDE.md**: Project-level context injection read at session start
- **MCP servers**: Plugin can bundle or reference MCP server configuration
- **Settings**: Plugin can define configuration schema

**Key hook for auto-detection:** The `PostToolUse` hook fires after each tool call, allowing the plugin to analyze what just happened and decide if it's worth remembering. The `Stop` hook fires at conversation end -- good for session summaries.

**Confidence note:** Claude Code plugin API may have evolved. Verify exact hook signatures, available event data, and plugin manifest format before implementation.

### AI Agent Memory Patterns (HIGH confidence -- well-established patterns)

Effective agent memory systems in knowledge bases typically include:

| Pattern | Description | This Project |
|---------|-------------|-------------|
| **Episodic memory** | Records of specific events/conversations | Session summaries, decisions made |
| **Semantic memory** | General knowledge and facts | Vault conventions, user preferences |
| **Procedural memory** | How to do things | "How to navigate this vault", "User prefers X format" |
| **Working memory** | Current session context | Loaded from persistent memories at session start |
| **Memory consolidation** | Merging/updating memories over time | Agent reviews and updates its memories periodically |
| **Relevance filtering** | Loading only relevant memories | Tag-based or path-based memory retrieval |

The existing memory system covers episodic and semantic memory. The differentiator is adding procedural memory (agent learns vault navigation patterns) and working memory (auto-loading relevant context at session start).

## Sources

- Existing codebase analysis (HIGH confidence)
- PROJECT.md requirements (HIGH confidence)
- SPECIFICATION.md feature set (HIGH confidence)
- Training data on Obsidian CLI, Claude Code plugins, AI memory patterns (MEDIUM confidence)
- No web verification was possible -- WebSearch, WebFetch, and Brave Search were all unavailable

**Research flags for roadmap:**
- Obsidian CLI 1.8+ exact capabilities need official doc verification
- Claude Code plugin hook API needs current doc verification
- Headless Obsidian mode behavior and limitations need testing
