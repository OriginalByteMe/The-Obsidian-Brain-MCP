# Act: Obsidian Brain Claude Code Plugin Transformation

**Status**: Complete

## Success Patterns → Formalization

### Pattern: Claude Code Skill Structure

**Files**: `skills/*/SKILL.md`
**Description**: Template for creating skills that orchestrate MCP tools via instructions to Claude
**When to use**: Adding new slash commands to the plugin

```yaml
---
name: skill-name
description: When and why Claude should use this skill
argument-hint: "[argument description]"
user-invocable: true
allowed-tools:
  - mcp__obsidian-brain__get_brain_config   # Always first — respect autonomy
  - mcp__obsidian-brain__get_vault_config   # Always second — respect conventions
  - mcp__obsidian-brain__<tool>             # Skill-specific tools
  - mcp__obsidian-brain__record_session_activity  # Always last — track for dedup
---

## Purpose
What this skill does.

## Prerequisites
1. Call `get_brain_config` to load autonomy preferences
2. Call `get_vault_config` to load vault conventions

## Workflow
Step-by-step instructions for Claude (Claude follows these, not code).

## Output Format
Template for the generated note/entry.

## Conventions
Rules about tagging, naming, linking per vault conventions.
```

### Pattern: Lifecycle Hook Script

**Files**: `scripts/session-start.py`, `scripts/periodic-checkin.py`
**Description**: Template for hook scripts that read stdin JSON and output structured response JSON
**When to use**: Adding new lifecycle hooks to the plugin

```python
#!/usr/bin/env python3
"""Hook script template — runs as subprocess, must use stdlib only."""
import json
import sys

def main():
    # 1. Parse stdin JSON
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)  # Graceful exit on bad input

    session_id = hook_input.get("session_id", "")

    # 2. Check autonomy config — exit early if disabled
    # 3. Do lightweight work (file I/O, HTTP with timeout)
    # 4. Output JSON to stdout
    output = {
        "hookSpecificOutput": {
            "hookEventName": hook_input.get("hook_event_name", ""),
            "additionalContext": "Context for Claude..."
        }
    }
    json.dump(output, sys.stdout)

if __name__ == "__main__":
    main()
```

**Critical rule**: Hook scripts MUST use only Python stdlib. They run as subprocesses outside any virtual environment. No `httpx`, `yaml`, `pydantic`, etc. Use `urllib.request` for HTTP and `json` for config parsing.

### Pattern: MCP Tool with Session State Coordination

**File**: `src/obsidian_brain/tools/session.py`
**Description**: MCP tools that maintain both in-process state and temp file state for cross-process coordination
**When to use**: Tools that need to share state with hook scripts

```python
# In-process state (fast, within MCP server process)
_session_state: dict = { ... }

# Temp file state (cross-process, shared with hook scripts)
state_path = Path("/tmp") / f"obsidian-brain-{session_id}.json"

# Always update BOTH:
_session_state["entries"].append(entry)        # In-process
with open(state_path, "w") as f:               # Temp file
    fcntl.flock(f, fcntl.LOCK_EX)
    json.dump(state, f)
    fcntl.flock(f, fcntl.LOCK_UN)
```

### Pattern: Config Merge with Defaults

**File**: `src/obsidian_brain/tools/session.py`
**Description**: Read vault config and fill missing keys from hardcoded defaults
**When to use**: Any tool that reads plugin configuration

```python
DEFAULT_AUTONOMY = { ... }
DEFAULT_PLUGIN = { ... }

def _merge_config(vault_config: dict) -> dict:
    autonomy = {**DEFAULT_AUTONOMY, **vault_config.get("autonomy", {})}
    plugin = {**DEFAULT_PLUGIN, **vault_config.get("plugin", {})}
    return {**vault_config, "autonomy": autonomy, "plugin": plugin}
```

---

## Learnings → Global Rules

### Learning 1: Hook Scripts Run Outside Virtual Environments

**Context**: Design assumed hook scripts could use `httpx` and `yaml`. Implementation failed with `ModuleNotFoundError` because Claude Code runs hooks as bare `python3` subprocesses.
**Insight**: Hook scripts are sandboxed — they have only Python stdlib available. Any heavy lifting must go through MCP tools instead.
**Action**: All future hook scripts must be stdlib-only. If complex vault operations are needed, the hook should output `additionalContext` that instructs Claude to call an MCP tool, rather than doing the work itself.

### Learning 2: Dual-Track State is Necessary for Cross-Process Coordination

**Context**: MCP tools run inside the server process. Hook scripts run as separate subprocesses. Both need to read/write session state.
**Insight**: A single state mechanism doesn't work. In-process dicts are invisible to subprocesses. Temp files are slow for the hot path within the MCP server.
**Action**: Always maintain both: in-process dict for fast MCP tool access, temp file for hook script coordination. Update both on every write.

### Learning 3: Python Module Filenames Must Use Underscores

**Context**: Design spec used `brain-state.py` for readability. Python cannot import modules with hyphens.
**Insight**: Shell scripts can use hyphens (`session-start.py` — not imported, only executed). Python modules that are imported must use underscores.
**Action**: Convention established — `scripts/` directory uses hyphens for executable scripts, underscores for importable modules.

### Learning 4: Skills as Instructions Massively Reduce Code Volume

**Context**: 5 skills were created as markdown files with zero Python code. Each skill is ~80-120 lines of instructions.
**Insight**: The skill-as-instructions pattern means adding new behaviors requires zero code changes — just a new SKILL.md file. The MCP server provides the tool API; skills orchestrate it.
**Action**: For any new plugin behavior, prefer adding a skill over adding code. Only add new MCP tools when the existing tool API is genuinely insufficient.

---

## Checklist Updates

### New Plugin Feature Checklist

- [ ] Does it need a new MCP tool, or can existing tools support it?
- [ ] If new MCP tool: follow `register_*_tools()` pattern in `tools/`
- [ ] If new skill: create `skills/<name>/SKILL.md` with frontmatter + instructions
- [ ] If new hook: add entry to `hooks/hooks.json`, create stdlib-only script in `scripts/`
- [ ] Update `get_brain_config` defaults if new config keys added
- [ ] Update `onboarding.py` `generate_config()` if config schema changed
- [ ] Add tests for new tools in `tests/test_session_tools.py`
- [ ] Add tests for new hooks in `tests/test_hooks.py`
- [ ] Update server instructions if new tools added
- [ ] Update README if user-facing behavior changed

### Hook Script Checklist

- [ ] Uses only Python stdlib (no httpx, yaml, pydantic)
- [ ] Parses stdin JSON with graceful fallback on bad input
- [ ] Checks autonomy config before doing work (early exit if disabled)
- [ ] Has timeout-safe HTTP calls (< 3 seconds for API calls)
- [ ] Outputs valid JSON to stdout (or nothing for no-op)
- [ ] Exits 0 on success, 2 on blocking error
- [ ] Handles missing vault/API gracefully (no crash, informative message)

### Skill Checklist

- [ ] YAML frontmatter with `name`, `description`, `user-invocable: true`
- [ ] `allowed-tools` lists every MCP tool the skill will use
- [ ] First step: `get_brain_config` (autonomy) + `get_vault_config` (conventions)
- [ ] Last step: `record_session_activity` (for deduplication tracking)
- [ ] Instructions reference `$ARGUMENTS` for user input
- [ ] Output format section shows expected note/entry structure
- [ ] Convention rules mention vault naming, tagging, and folder placement

---

## Documentation Updates

- [x] Server instructions — Added Session & Plugin tools, skills, hooks, brag doc sections
- [x] README.md — Added plugin installation, skills table, hooks description, autonomy config
- [x] Design doc — `docs/design-plugin-architecture.md` (reference architecture)
- [x] Workflow doc — `docs/workflow_plugin_implementation.md` (implementation plan)
- [x] Requirements doc — `docs/brainstorm-plugin-requirements.md` (original requirements)
- [ ] Consider adding a `CONTRIBUTING.md` with plugin extension guide (future)

---

## Follow-up Tasks

| Task | Priority | Notes |
|------|----------|-------|
| Fix pre-existing `test_resources.py` broken import | Medium | From previous PDCA's reverted vault_access module. Clean up or delete. |
| End-to-end smoke test with live Obsidian vault | High | Unit tests mock HTTP; need real vault to validate full flow |
| Test plugin installation via marketplace on fresh machine | High | Verify `uvx --from git+...` resolves, env vars propagate |
| Add `/organize-inbox` skill (from brainstorm) | Low | Was considered but not prioritized for v0.2.0 |
| Add `/format-note` skill (from brainstorm) | Low | Was considered but not prioritized for v0.2.0 |
| Multi-user vault support | Low | Deferred per Q4 resolution. Revisit when team use case emerges. |
| Configurable brag doc categories via `/brain-config` | Medium | Config key exists; need to verify `/brain-config` handles list values |
| Session-end hook: test Haiku prompt evaluation accuracy | Medium | Prompt-type hook can't be unit tested; needs manual validation |
| Publish to a standalone marketplace repo | Low | Current self-contained approach works; separate repo only if adoption grows |

---

## Retrospective Summary

**What went well**:
- Three-document pipeline (brainstorm → design → workflow) eliminated all ambiguity before implementation started
- Bottom-up build order meant zero blocking dependencies between phases
- Additive-only approach preserved all existing functionality with zero regressions
- 5 clean atomic commits map 1:1 to implementation phases, making history easy to navigate
- 16/16 tests passing on first full run (after 4 minor fixes during development)

**What could improve**:
- Design doc should have flagged the stdlib-only constraint for hook scripts — this is a fundamental Claude Code limitation that the architecture should have accounted for upfront
- The naming convention (hyphens vs underscores in `scripts/`) should have been established in the design phase, not discovered during implementation
- Pre-existing broken tests should be cleaned up before starting new work to avoid confusion

**Key takeaway**: The skills-as-instructions architecture is remarkably powerful. Five new user-facing behaviors were added with zero Python code — only markdown instruction files. The MCP server provides the API surface; skills orchestrate it. This pattern should be the default for all future plugin behaviors. Reserve new MCP tools for cases where the existing API genuinely can't express the operation.
