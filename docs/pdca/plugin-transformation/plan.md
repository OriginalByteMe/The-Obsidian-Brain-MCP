# Plan: Obsidian Brain Claude Code Plugin Transformation

**Created**: 2026-02-05
**Source**: `docs/brainstorm-plugin-requirements.md`, `docs/design-plugin-architecture.md`, `docs/workflow_plugin_implementation.md`

## Hypothesis

Transform Obsidian Brain from a standalone MCP server into a distributable Claude Code plugin that proactively maintains the user's Obsidian vault. The plugin bundles the existing MCP server alongside skills (slash commands), hooks (lifecycle automation), and a session tracking system — turning passive vault tools into an active knowledge management companion.

**Why this approach**: The Claude Code plugin system provides native support for skills (instructions to the LLM), hooks (lifecycle events), and MCP servers (tools). By packaging all three together, the LLM can both *respond* to vault requests AND *proactively* capture learnings, log sessions, and maintain a brag doc as a byproduct of normal coding sessions.

**Key architectural decision**: Skills are *instructions to Claude* (markdown), not code. The MCP server holds all logic. Hook scripts are lightweight Python that check conditions and provide context. This separation means each layer can be developed, tested, and shipped independently.

## Expected Outcomes (Quantitative)

| Metric | Expected | Notes |
|--------|----------|-------|
| Plugin installable via marketplace | Yes | Single command: `/plugin install obsidian-brain@marketplace` |
| Existing MCP tools preserved | 32/32 | Zero regressions — fully additive transformation |
| New MCP tools added | 5 | Session tracking, config, brag doc |
| Skills (slash commands) | 5 | `/document-it`, `/capture-learning`, `/review-session`, `/brain-status`, `/brain-config` |
| Lifecycle hooks | 3 | Session start, session end evaluation, periodic check-in |
| New files created | 16 | Manifests, skills, hooks, scripts, tools, tests |
| Existing files modified | 5 | server.py, onboarding.py, .mcp.json, __init__.py, pyproject.toml |
| Existing files broken | 0 | All changes are additive |
| Tests passing | 100% | New tests for session tools and hook scripts |

## Phases

### Phase 1: Plugin Scaffold
- **New files**: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `hooks/hooks.json` (stub)
- **Modify**: `.mcp.json` (portable `uvx` config), `__init__.py` + `pyproject.toml` (version bump)
- **Risk**: Low — no Python code changes, just manifests and config
- **Checkpoint**: `claude --plugin-dir .` loads without error

### Phase 2: Session State & Configuration Tools
- **New files**: `scripts/brain-state.py`, `src/obsidian_brain/tools/session.py`
- **Modify**: `src/obsidian_brain/server.py` (register new tools)
- **Risk**: Low — additive MCP tools, follows existing tool registration pattern
- **Checkpoint**: 5 new tools callable via MCP, existing 32 tools unaffected

### Phase 3: Hook Scripts
- **New files**: `scripts/session-start.py`, `scripts/periodic-checkin.py`
- **Modify**: `hooks/hooks.json` (populate with full config)
- **Risk**: Medium — hooks interact with Obsidian REST API directly; must handle vault offline gracefully
- **Checkpoint**: Scripts produce valid JSON output given mock stdin; hooks.json references valid scripts

### Phase 4: Skills
- **New files**: 5 `skills/*/SKILL.md` files
- **Risk**: Low — pure markdown, no code; skills reference MCP tools from Phase 2
- **Checkpoint**: Skills appear in Claude Code `/` menu when plugin loaded

### Phase 5: Integration Testing & Polish
- **New files**: `tests/test_session_tools.py`, `tests/test_hooks.py`
- **Modify**: `src/obsidian_brain/onboarding.py` (config extension), `server.py` (instructions), `README.md`
- **Risk**: Low — testing and documentation
- **Checkpoint**: All tests pass, README documents plugin usage

## Risks & Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| `uvx --from git+...` fails for some users | MCP server won't start | Medium | Document alternative local `.mcp.json` config; test on fresh system |
| `${CLAUDE_PLUGIN_ROOT}` not resolved | Hook scripts can't find brain-state.py | Low | Scripts fall back to relative paths; document in troubleshooting |
| Obsidian not running when hooks fire | Session-start hangs or errors | High | 3-second HTTP timeout; graceful "Brain offline" message |
| Stop hook fires on every response (too frequent) | Periodic check-in annoys user | Medium | First action in script is timestamp check — exits in <100ms for no-op case |
| Brag doc auto-detection finds wrong note | Entries written to wrong place | Low | Use `brain-managed: true` frontmatter tag; `/brain-config` allows explicit path |
| Session state temp file conflicts | State corruption between concurrent sessions | Low | Files keyed by unique `session_id`; file locking on all writes |
| Plugin system changes in future Claude Code versions | Plugin breaks on update | Medium | Pin to documented plugin.json schema; minimal hook complexity |

## Rollback Plan

The entire transformation is additive. Rollback per phase:

| Phase | Rollback Action |
|-------|----------------|
| Phase 1 | Delete `.claude-plugin/`, `hooks/`, revert `.mcp.json` and version numbers |
| Phase 2 | Delete `scripts/brain-state.py`, `tools/session.py`; remove import from `server.py` |
| Phase 3 | Delete `scripts/session-start.py`, `scripts/periodic-checkin.py`; empty `hooks/hooks.json` |
| Phase 4 | Delete `skills/` directory entirely |
| Phase 5 | Delete test files; revert onboarding.py, README.md |

**Nuclear rollback**: `git revert` back to the commit before Phase 1. All existing functionality is untouched.

## Dependencies Between Phases

```
Phase 1 ─────► Phase 2 ─────┬──► Phase 3
                             │
                             └──► Phase 4
                                    │
              Phase 3 ──────┬──► Phase 5
              Phase 4 ──────┘
```

- Phase 2 depends on Phase 1 (needs plugin structure)
- Phases 3 and 4 depend on Phase 2 (need session tools) but NOT on each other
- Phase 5 depends on Phases 3 and 4 (integration tests cover both)

## Success Criteria

1. User can install the plugin with two commands (add marketplace + install)
2. `/brain-status` shows vault connection and today's daily note summary
3. `/document-it [topic]` creates a properly tagged, linked note in the correct vault location
4. `/capture-learning` analyzes the session and creates a structured learning note
5. Session start hook displays "Brain connected" with today's context
6. Periodic check-in fires after 30 minutes of activity (configurable)
7. Session end evaluator correctly identifies noteworthy sessions
8. All autonomy settings are configurable via `/brain-config`
9. Brag doc accumulates entries without duplicates
10. Existing standalone MCP usage is completely unaffected
