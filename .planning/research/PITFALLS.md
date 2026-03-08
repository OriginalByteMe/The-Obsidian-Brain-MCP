# Domain Pitfalls

**Domain:** Obsidian CLI MCP server + Claude Code plugin (AI agent memory system)
**Researched:** 2026-03-08
**Confidence:** MEDIUM (based on training data and codebase analysis; web verification unavailable)

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: CLI Subprocess Output Parsing Fragility

**What goes wrong:** The current `ObsidianClient` returns structured JSON from a well-defined REST API with typed HTTP status codes, content-type headers, and consistent response shapes. Replacing this with CLI subprocess calls means parsing stdout/stderr text output, which is inherently fragile. CLI output formats change between versions, may include unexpected warnings or prompts, and differ across platforms. Teams build parsers against one version's output and discover they break silently on updates.

**Why it happens:** Developers treat CLI output as a stable API contract when it is not. The Obsidian CLI is relatively new (1.8+) and its output format is not guaranteed to be stable across minor versions. Unlike a REST API with a formal spec, CLI output is designed for humans.

**Consequences:** Silent data corruption (parsing wrong fields), false "success" when operation failed, complete breakage on Obsidian updates. The current codebase has 15+ methods on `ObsidianClient` that all parse structured JSON responses -- each one becomes a fragile text parser.

**Prevention:**
- Use `--format json` or equivalent structured output flags if the Obsidian CLI supports them. Verify this before committing to the CLI approach.
- Build a thin adapter layer (`CLIClient`) that isolates all output parsing in one place, separate from business logic. Never parse CLI output inline in tool handlers.
- Write integration tests against actual CLI output for each command, not just mocked strings.
- Pin the minimum Obsidian version and document which CLI output format you target.
- If the CLI does NOT support structured output, seriously reconsider whether direct filesystem access (reading .md files) combined with CLI for plugin-dependent operations (search, Dataview) is a better hybrid.

**Detection:** Tests pass but users report "Note not found" for notes that exist. Parsing errors in logs. Operations succeed but return empty/mangled content.

**Phase:** CLI migration phase -- must be validated in the very first spike before building the full adapter.

---

### Pitfall 2: Obsidian Process Lifecycle Mismanagement (Headless Mode)

**What goes wrong:** The project plans a "headless Obsidian fallback" for when the desktop app isn't running. Obsidian is an Electron application -- spawning it headlessly means managing a full Chromium process tree. Developers treat this like spawning a simple CLI tool, but Electron apps have complex startup sequences, GPU process spawning, crash reporters, and non-trivial shutdown behavior. Zombie processes accumulate, ports get locked, and the system runs out of resources.

**Why it happens:** Electron headless mode (`--no-sandbox`, `--headless`, `--disable-gpu`) is not the same as running a lightweight daemon. Obsidian loads plugins, indexes vaults, and may display dialogs (update prompts, vault migration) that block headless operation. There is no official "headless daemon" mode in Obsidian -- it is a workaround.

**Consequences:** Zombie Obsidian processes consuming RAM/CPU. Port conflicts when multiple instances spawn. Vault lock files preventing access. Users unable to open Obsidian normally because headless instance holds the vault lock. System instability on machines with limited resources.

**Prevention:**
- Implement a proper process manager with PID file tracking, health checks, and forced cleanup on exit.
- Use `atexit` handlers AND signal handlers (SIGTERM, SIGINT) to ensure cleanup happens even on crashes.
- Implement a single-instance lock: check if Obsidian is already running (desktop or headless) before spawning.
- Set aggressive timeouts on startup: if Obsidian headless doesn't respond to CLI within 30 seconds, kill and report an error rather than hanging.
- Store PID files in a well-known location (e.g., `~/.obsidian-brain/headless.pid`) and implement stale PID detection.
- Consider whether headless is worth the complexity: the CLI may work without a running Obsidian instance for basic file operations. Test this assumption first.

**Detection:** `ps aux | grep obsidian` shows multiple zombie processes. Users report Obsidian won't open ("vault is locked"). Memory usage climbs over time. MCP server hangs on operations.

**Phase:** Headless fallback phase -- should be a separate, optional component that can be completely disabled.

---

### Pitfall 3: Leaky Interface Abstraction During Migration

**What goes wrong:** The current `ObsidianClient` has a clean async context manager pattern (`async with ObsidianClient() as client:`) used in every single tool handler. The temptation is to make the new CLI client "drop-in compatible" by keeping the same interface but changing internals. This fails because CLI subprocess calls have fundamentally different semantics: no persistent connection, different error modes (exit codes vs HTTP status), different latency profiles (process spawn overhead), and no streaming.

**Why it happens:** The existing codebase creates a new `ObsidianClient()` context manager for every single tool call (visible in `vault.py` -- each tool does `async with ObsidianClient() as client:`). With HTTP, this is cheap (connection pooling handles it). With CLI subprocesses, each call spawns a new process with ~100-500ms overhead. If 5 operations need to happen (e.g., cache refresh reads every note), this becomes N subprocess spawns instead of N HTTP requests on a pooled connection.

**Consequences:** 10-50x slowdown on operations like `refresh_vault_structure` which currently makes N sequential HTTP requests (one per note). Cache refresh on a 500-note vault goes from ~10 seconds to ~5 minutes. Users abandon the tool.

**Prevention:**
- Do NOT try to make the CLI client a drop-in replacement. Define a new `VaultBackend` protocol/ABC that both `HTTPBackend` and `CLIBackend` implement, with batch operation support.
- For the CLI backend, implement batch operations where possible (e.g., if the CLI supports listing all notes with metadata in one command, use that instead of N individual calls).
- Consider a hybrid approach: use direct filesystem reads for note content (they are just .md files), and CLI only for operations that need Obsidian's plugin ecosystem (search, Dataview queries, template rendering).
- Profile early: measure actual CLI subprocess latency on the target platform before committing to the architecture.

**Detection:** Cache refresh takes minutes instead of seconds. Users report the MCP server is "slow" or "times out." Tool calls that used to be instant now have visible latency.

**Phase:** CLI migration phase -- the backend abstraction should be designed before any CLI code is written.

---

### Pitfall 4: Memory System Becomes a Junk Drawer

**What goes wrong:** The agent memory system (currently `MemoryManager` storing markdown files in `.obsidian-brain/memories/`) has no retrieval strategy beyond listing files. As the agent stores more memories, every retrieval becomes "scan all memories" which is O(n) and returns irrelevant results. The Claude Code plugin's "auto-detection of noteworthy moments" exacerbates this by creating many low-value memories that dilute useful ones.

**Why it happens:** Memory creation is easy and feels productive. Memory retrieval and pruning are hard problems that get deferred. The current `MemoryManager` has `list_from_files()` and `parse_memory()` but no search, no relevance scoring, and no expiration. Without constraints, the agent stores everything and retrieves nothing useful.

**Consequences:** Context window pollution -- the agent loads 50 memories when only 2 are relevant, wasting tokens and degrading response quality. Memory folder grows to hundreds of files. Agent behavior degrades over time as irrelevant memories accumulate.

**Prevention:**
- Define a memory taxonomy from day one: `workflow` (how user prefers things), `fact` (specific knowledge), `preference` (user preferences), `session` (ephemeral context). Each type gets different retention rules.
- Implement memory caps: maximum N memories per type, with oldest-first eviction or explicit user pruning.
- Build retrieval with relevance: at minimum, tag-based filtering so the agent can request "memories about Python testing" not "all memories." Consider frontmatter-based querying.
- The "auto-detection" feature MUST have a quality threshold. Not every conversation is worth remembering. Require the plugin to justify why something is noteworthy before storing it.
- Implement a "memory review" tool that lets the user see and prune what the agent has stored. Permission-based writing (already planned) helps but is not sufficient -- the user also needs to manage accumulated memories.

**Detection:** Memory folder has 100+ files after a few weeks. Agent responses mention irrelevant past context. Token usage spikes as memory loading grows. User notices agent "remembering" wrong things.

**Phase:** Memory system design phase AND Claude Code plugin phase -- the taxonomy and caps must exist before the auto-detection feature is built.

---

### Pitfall 5: Claude Code Plugin Hooks as Invisible Side Effects

**What goes wrong:** Claude Code hooks (PreToolUse, PostToolUse, Notification, etc.) execute code in response to agent actions. When hooks silently create notes, modify vault state, or store memories without clear user visibility, the user loses trust. Worse, hooks that fail silently cause inconsistent state -- the agent thinks a memory was stored but the hook errored.

**Why it happens:** Hooks are designed to be non-blocking and transparent. Developers make them fire-and-forget for performance. But vault operations can fail (Obsidian not running, CLI errors, disk full) and these failures are invisible in the hook execution context. The hook system also runs with the agent's permissions, not the user's explicit consent per-action.

**Consequences:** User discovers unexpected notes in their vault. Agent references memories that were never actually stored. Trust erosion leads to users disabling the plugin entirely. Debug nightmares when hook failures cause inconsistent state between what the agent "knows" and what the vault contains.

**Prevention:**
- Every hook that modifies vault state MUST log its action visibly (not just to stderr -- the user should see "Stored memory: X" in the conversation).
- Implement a "dry run" mode where hooks report what they would do without doing it, for user onboarding and debugging.
- Hook failures must propagate: if a memory store fails, the agent should know it failed (return error status from hook, not swallow).
- The "permission-based writing" requirement in PROJECT.md is essential -- enforce it in the hook layer, not just in individual tools. No hook should write to the vault without user approval during the initial rollout.
- Keep hooks stateless: a hook should not depend on the outcome of a previous hook. Each hook invocation should be self-contained.

**Detection:** Users report "ghost notes" appearing in their vault. Agent references context the user never approved. Hook errors visible in Claude Code logs but not in conversation. Users say "I don't trust this plugin."

**Phase:** Claude Code plugin phase -- hook architecture must be designed with error handling and visibility before any auto-detection features.

## Moderate Pitfalls

### Pitfall 6: CLI Command Injection via Unsanitized Note Paths

**What goes wrong:** Note paths come from user input and existing vault content (wikilinks). The current codebase passes paths directly into HTTP URLs (`f"/vault/{path}"`), which is safe because URL encoding handles special characters. When these same paths get interpolated into CLI commands (`obsidian-cli read "path"`), shell metacharacters in note titles cause command injection. Obsidian note titles can contain backticks, dollar signs, semicolons, and other dangerous characters.

**Prevention:**
- NEVER use `shell=True` with subprocess calls. Always pass command arguments as a list: `subprocess.run(["obsidian", "read", path])`.
- Use `shlex.quote()` as a defense-in-depth measure even with list-based subprocess calls.
- Validate/sanitize paths before CLI invocation. The existing `_sanitize_name()` in `MemoryManager` is a good pattern but needs to be applied universally.
- Write explicit tests with adversarial path names: `"test; rm -rf /".md`, `"$(whoami).md"`, `` "`id`.md" ``.

**Phase:** CLI migration phase -- must be in the first implementation, not added later.

---

### Pitfall 7: Vault Structure Cache Staleness After CLI Writes

**What goes wrong:** The current cache (`VaultCache`) is explicitly refreshed via `refresh_vault_structure`. When the MCP server writes a note via CLI, the in-memory cache doesn't know about it. Subsequent reads from cache return stale data. The problem is worse than with the REST API because CLI writes might not even confirm success reliably.

**Prevention:**
- Invalidate specific cache entries after write operations (note create, update, delete). Don't require a full refresh.
- Add an `invalidate(path)` method to `VaultCache` that removes a specific note from the cache and marks related indexes (backlinks, tags) as dirty.
- For the CLI backend, verify write success by checking the file exists/was modified after the CLI command returns.
- Consider a lightweight file watcher (using `watchdog`) as an optional cache invalidation mechanism, even though real-time watching is out of scope for v1. A periodic poll (every 60s) is a simpler alternative.

**Phase:** CLI migration phase -- cache invalidation strategy should be part of the backend abstraction design.

---

### Pitfall 8: Claude Code Plugin Distribution and Versioning

**What goes wrong:** Claude Code plugins have specific packaging and discovery conventions. Building the plugin as a tightly-coupled extension of the MCP server creates versioning nightmares: updating the plugin requires updating the MCP server, and vice versa. Users with different Claude Code versions get incompatible plugin behavior.

**Prevention:**
- The plugin and MCP server should be independently versioned and deployable. The plugin communicates with the MCP server over the standard MCP protocol, not via internal imports.
- Pin Claude Code plugin API compatibility in the plugin manifest. Test against multiple Claude Code versions.
- Keep the plugin thin: it should contain hooks, slash command definitions, and CLAUDE.md content. All vault logic lives in the MCP server.
- Document the minimum Claude Code version required and fail gracefully with a clear error on older versions.

**Phase:** Plugin architecture phase -- separation must be designed upfront.

---

### Pitfall 9: Onboarding Detection Overconfidence

**What goes wrong:** The existing onboarding system detects vault patterns (PARA, Zettelkasten, etc.) and generates configuration. When the Claude Code plugin "learns vault conventions" and "builds its own memory," incorrect pattern detection cascades into the agent creating notes that violate the user's actual organizational system. The agent confidently creates a "Projects/Active/..." note in a vault that uses flat structure.

**Prevention:**
- Pattern detection should output confidence scores, not binary classifications. "70% likely PARA structure" is more useful than "PARA detected."
- Always show the user what was detected and let them correct it before the agent acts on it. Store corrections as high-priority memories.
- Make vault convention memories editable and overridable. The user should be able to say "I don't use PARA, I use flat folders" and have the agent respect that permanently.
- Start with conservative defaults: create notes in a safe namespace (e.g., `Obsidian Brain/` prefix) until the user explicitly confirms the agent should write to their organizational structure.

**Phase:** Vault structure learning phase -- detection must include confidence and user confirmation.

---

### Pitfall 10: Subprocess Timeout and Cancellation Handling

**What goes wrong:** CLI subprocess calls can hang indefinitely if Obsidian is unresponsive, the vault is locked, or the CLI encounters an interactive prompt. The current HTTP client has a 30-second timeout (`timeout=30.0`). Subprocess calls default to no timeout.

**Prevention:**
- Always set explicit timeouts on `asyncio.create_subprocess_exec()` using `asyncio.wait_for()` or `process.communicate(timeout=...)`.
- Set default timeout to 30 seconds (matching current HTTP behavior) with per-operation overrides (cache refresh may need longer).
- On timeout, explicitly kill the subprocess (`process.kill()`) and clean up. Don't leave orphaned processes.
- For operations that legitimately take longer (full vault scan), implement progress reporting or chunked execution.

**Phase:** CLI migration phase -- timeout handling must be in the base `CLIBackend` implementation.

## Minor Pitfalls

### Pitfall 11: YAML Frontmatter Round-Trip Fidelity

**What goes wrong:** The `MemoryManager` and frontmatter utilities use `yaml.dump()` and `yaml.safe_load()` for frontmatter. YAML round-tripping is lossy: comments are stripped, key ordering changes, multiline strings get reformatted, and special characters get escaped differently. Users who manually edit memory files or notes with specific YAML formatting find their formatting destroyed after the agent touches the file.

**Prevention:**
- Use `ruamel.yaml` instead of `PyYAML` for round-trip-safe YAML handling, or only modify specific keys rather than dumping the entire frontmatter.
- For user-facing notes, prefer appending content rather than rewriting the entire note.
- For agent-only files (memories), YAML formatting drift is acceptable but should be consistent.

**Phase:** Any phase that touches frontmatter -- consider switching to `ruamel.yaml` early.

---

### Pitfall 12: Docker Deployment Incompatible with CLI Approach

**What goes wrong:** The existing Docker deployment (`Dockerfile`, `docker-compose.yml`) assumes the MCP server only needs network access to the REST API. Replacing the REST API with a local CLI means the Obsidian binary must be available inside the container OR the container must somehow access the host's CLI. Neither is straightforward.

**Prevention:**
- Acknowledge that Docker deployment may not be viable for the CLI-based approach. The CLI requires access to the local Obsidian installation and vault filesystem.
- If Docker is kept, it will need volume mounts for the vault AND access to the host's Obsidian CLI binary (complex and fragile).
- Consider dropping Docker support for v2 and relying on direct Python installation via `uv`/`pip`. Or maintain the REST API backend as a Docker-compatible alternative.

**Phase:** Architecture phase -- the Docker story must be rethought before CLI migration begins.

---

### Pitfall 13: MCP Tool Interface Backward Compatibility

**What goes wrong:** The project constraint says "existing MCP tool interfaces should remain stable." But changing the backend from REST to CLI may subtly change behavior: response timing, error messages, edge case handling. Existing users' workflows break even though the interface looks the same.

**Prevention:**
- Write integration tests that capture current behavior (response shapes, error messages, edge cases) BEFORE starting the migration. These become your backward compatibility contract.
- Use a feature flag or backend selector so users can switch between REST and CLI backends. Don't remove the REST backend immediately.
- Document any behavioral changes in release notes, even minor ones.

**Phase:** Pre-migration -- compatibility tests should be written first.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| CLI migration | Output parsing fragility (#1), performance regression (#3), command injection (#6) | Build thin adapter with structured output, profile early, sanitize all inputs |
| Headless Obsidian | Process lifecycle zombies (#2), timeout hangs (#10) | PID tracking, signal handlers, aggressive timeouts, make it optional |
| Claude Code plugin | Invisible side effects (#5), distribution coupling (#8) | Visible logging, permission gates, independent versioning |
| Memory system | Junk drawer accumulation (#4), staleness (#7) | Taxonomy, caps, relevance filtering, cache invalidation |
| Vault learning | Overconfident detection (#9) | Confidence scores, user confirmation, safe namespace defaults |
| Backend abstraction | Leaky interface (#3), Docker breakage (#12), backward compat (#13) | New protocol/ABC, feature flags, pre-migration compatibility tests |
| Frontmatter handling | YAML round-trip lossy (#11) | Use ruamel.yaml or surgical edits |

## Sources

- Codebase analysis: `src/obsidian_brain/client.py` (HTTP client pattern), `src/obsidian_brain/cache.py` (cache architecture), `src/obsidian_brain/memory.py` (memory system), `src/obsidian_brain/tools/vault.py` (tool handler patterns)
- Project context: `.planning/PROJECT.md` (requirements, constraints, decisions)
- Specification: `SPECIFICATION.md` (full API surface, data models, architecture)
- Python subprocess best practices: training data (MEDIUM confidence -- patterns are well-established but Obsidian CLI specifics are unverified)
- Electron headless behavior: training data (MEDIUM confidence -- general Electron patterns are known but Obsidian-specific headless behavior is LOW confidence)
- Claude Code plugin conventions: training data (LOW confidence -- plugin system may have evolved since training cutoff)
