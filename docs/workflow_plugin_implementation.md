# Obsidian Brain — Plugin Implementation Workflow

> **Status**: Implementation Plan
> **Date**: 2026-02-05
> **Input**: [design-plugin-architecture.md](./design-plugin-architecture.md)
> **Approach**: Bottom-up — build foundation layers first, integration layers last
> **Estimated Files**: 16 new files, 3 modified files

---

## Phase Overview

```
Phase 1: Plugin Scaffold              [3 new files, 1 modified]
    │     No Python changes. Just manifests and config.
    │
    ▼
Phase 2: Session State & Config       [2 new files, 2 modified]
    │     New MCP tools. Foundation for all skills/hooks.
    │
    ▼
Phase 3: Hook Scripts                  [4 new files]
    │     Lifecycle automation. Depends on Phase 2 state module.
    │
    ▼
Phase 4: Skills                        [5 new files]
    │     User-facing commands. Depends on Phase 2 tools.
    │
    ▼
Phase 5: Integration Testing & Polish  [0 new files, modifications]
          End-to-end validation. Config extension.
```

**Dependency rule**: Each phase can be completed, tested, and committed independently. Phases 3 and 4 are independent of each other (both depend on Phase 2, not on each other) and could be done in parallel.

---

## Phase 1: Plugin Scaffold

**Goal**: Transform the repo into a valid Claude Code plugin without changing any Python code.

**Checkpoint**: `claude plugin validate .` passes. Plugin is installable locally via `claude --plugin-dir .`

### Step 1.1 — Create plugin manifest

**File**: `.claude-plugin/plugin.json` (NEW)

```json
{
  "name": "obsidian-brain",
  "version": "0.2.0",
  "description": "Intelligent Obsidian vault companion — captures learnings, logs sessions, and maintains your knowledge base as you code",
  "author": {
    "name": "Noah R",
    "url": "https://github.com/OriginalByteMe"
  },
  "repository": "https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP",
  "license": "MIT",
  "keywords": ["obsidian", "knowledge-management", "notes", "daily-notes", "brag-doc"],
  "mcpServers": "./.mcp.json",
  "hooks": "./hooks/hooks.json"
}
```

**Verification**: File exists, valid JSON, `name` field present.

### Step 1.2 — Create marketplace manifest

**File**: `.claude-plugin/marketplace.json` (NEW)

```json
{
  "name": "obsidian-brain-marketplace",
  "owner": {
    "name": "Noah R",
    "url": "https://github.com/OriginalByteMe"
  },
  "metadata": {
    "description": "Obsidian Brain — intelligent vault companion for Claude Code",
    "version": "1.0.0"
  },
  "plugins": [
    {
      "name": "obsidian-brain",
      "source": ".",
      "description": "MCP server, skills, and hooks for Obsidian vault management",
      "version": "0.2.0",
      "category": "productivity",
      "tags": ["obsidian", "knowledge-management", "notes"]
    }
  ]
}
```

**Verification**: Valid JSON, plugin source "." resolves to the plugin root.

### Step 1.3 — Update MCP server configuration

**File**: `.mcp.json` (MODIFY)

Replace current contents with plugin-portable configuration:

```json
{
  "mcpServers": {
    "obsidian-brain": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP",
        "obsidian-brain"
      ],
      "env": {
        "OBSIDIAN_API_KEY": "${OBSIDIAN_API_KEY}"
      }
    }
  }
}
```

**Verification**: Valid JSON. `uvx --from git+... obsidian-brain --help` works (tests that the package is installable from git).

### Step 1.4 — Create placeholder hooks.json

**File**: `hooks/hooks.json` (NEW)

Start with an empty hooks config (will be populated in Phase 3):

```json
{
  "description": "Obsidian Brain lifecycle hooks for session tracking and knowledge capture",
  "hooks": {}
}
```

**Verification**: Valid JSON, referenced by plugin.json.

### Step 1.5 — Version bump

**File**: `src/obsidian_brain/__init__.py` (MODIFY)

Change `__version__` from `"0.1.0"` to `"0.2.0"`.

**File**: `pyproject.toml` (MODIFY)

Change `version` from `"0.1.0"` to `"0.2.0"`.

### Phase 1 Checkpoint

```bash
# Verify plugin structure
ls .claude-plugin/plugin.json       # exists
ls .claude-plugin/marketplace.json  # exists
ls hooks/hooks.json                 # exists

# Validate JSON
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"
python3 -c "import json; json.load(open('.claude-plugin/marketplace.json'))"
python3 -c "import json; json.load(open('.mcp.json'))"
python3 -c "import json; json.load(open('hooks/hooks.json'))"

# Test local plugin loading
claude --plugin-dir . --help  # Should not error

# Verify existing MCP server still works
uv run python -m obsidian_brain.server --help 2>&1 || echo "Server module loads"
```

**Commit**: `feat: add Claude Code plugin scaffold with manifests and marketplace config`

---

## Phase 2: Session State & Configuration Tools

**Goal**: Add the MCP tools that skills and hooks depend on. This is the foundation layer.

**Checkpoint**: New tools registered and callable. Existing tools unaffected.

### Step 2.1 — Create session state manager

**File**: `scripts/brain-state.py` (NEW)

Shared Python module for session state management. Used by hook scripts (Phase 3) AND importable by MCP tools.

```python
"""
Session state management for Obsidian Brain hooks and tools.

Provides atomic read/write of session state stored in temp files.
State is keyed by session_id and persists for the duration of a
Claude Code session.
"""

import fcntl
import json
import os
from datetime import datetime
from pathlib import Path

STATE_DIR = Path("/tmp")


def get_state_path(session_id: str) -> Path:
    """Get the temp file path for a session's state."""
    return STATE_DIR / f"obsidian-brain-{session_id}.json"


def read_state(session_id: str) -> dict:
    """Read session state, returning defaults if no state exists."""
    path = get_state_path(session_id)
    if not path.exists():
        return _default_state(session_id)
    with open(path) as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            data = json.load(f)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return data


def write_state(session_id: str, state: dict) -> None:
    """Write session state atomically with file locking."""
    path = get_state_path(session_id)
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(state, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _default_state(session_id: str) -> dict:
    """Return default state for a new session."""
    now = datetime.now().isoformat()
    return {
        "session_id": session_id,
        "started_at": now,
        "last_checkin": now,
        "notes_created": [],
        "daily_entries": [],
        "brag_entries": [],
    }


def read_vault_config(
    api_key: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> dict:
    """
    Read Obsidian Brain config from the vault via REST API.

    Uses environment variables as defaults:
    - OBSIDIAN_API_KEY
    - OBSIDIAN_HOST (default: 127.0.0.1)
    - OBSIDIAN_PORT (default: 27124)
    """
    import httpx
    import yaml

    api_key = api_key or os.getenv("OBSIDIAN_API_KEY", "")
    host = host or os.getenv("OBSIDIAN_HOST", "127.0.0.1")
    port = port or int(os.getenv("OBSIDIAN_PORT", "27124"))

    url = f"https://{host}:{port}/vault/Obsidian Brain/config.yml"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/markdown",
    }
    try:
        resp = httpx.get(url, headers=headers, verify=False, timeout=3.0)
        if resp.status_code == 200:
            return yaml.safe_load(resp.text) or {}
    except Exception:
        pass
    return {}


# Default plugin configuration (used when vault config is missing/incomplete)
DEFAULT_AUTONOMY = {
    "session_start_context": "silent",
    "session_end_learning_capture": "prompt",
    "session_end_daily_log": "silent",
    "brag_doc_update": "prompt",
    "periodic_checkin": "prompt",
}

DEFAULT_PLUGIN = {
    "checkin_interval_minutes": 30,
    "daily_note_heading": "## Claude Code Sessions",
    "brag_doc_path": None,
    "brag_doc_categories": [
        "Features Built",
        "Bugs Fixed",
        "Improvements",
        "Key Learnings",
    ],
    "learning_note_folder": None,
    "session_log_format": "summary",
}
```

**Verification**: `python3 -c "import sys; sys.path.insert(0, 'scripts'); import brain_state; print(brain_state.read_state('test'))"` prints default state.

### Step 2.2 — Create session MCP tools

**File**: `src/obsidian_brain/tools/session.py` (NEW)

Five new MCP tools for session tracking, config, and brag doc management.

**Tool signatures** (from design doc):
1. `get_brain_config() -> str` — Read autonomy + plugin config
2. `update_brain_config(key: str, value: str) -> str` — Update config value
3. `get_session_state() -> str` — Read current session tracking state
4. `record_session_activity(activity_type: str, summary: str, note_paths: list[str] | None) -> str` — Track an activity
5. `append_to_brag_doc(category: str, description: str, links: list[str] | None) -> str` — Add brag doc entry

**Implementation notes**:
- `get_brain_config` reads `Obsidian Brain/config.yml` via `ObsidianClient`, merges with defaults
- `update_brain_config` reads existing config, updates the key using dot-notation, writes back
- `get_session_state` reads from `/tmp/obsidian-brain-{session_id}.json` (in-process fallback if no file)
- `record_session_activity` writes to both session state file AND optionally to daily note
- `append_to_brag_doc` reads brag doc, checks for duplicates, appends entry under correct heading

**Key dependency**: Uses existing `ObsidianClient` for all vault I/O. Uses `frontmatter.py` utils for parsing/writing frontmatter. Uses existing `create_daily_entry` pattern for daily note integration.

**Verification**: `uv run python -c "from obsidian_brain.tools.session import register_session_tools; print('OK')"` succeeds.

### Step 2.3 — Register session tools in server

**File**: `src/obsidian_brain/server.py` (MODIFY)

Add two lines:
1. Import: `from .tools.session import register_session_tools`
2. Registration: `register_session_tools(server)` (after existing registrations)

**Verification**: `uv run python -c "from obsidian_brain.server import server; print(f'{len(server._tool_manager._tools)} tools')"` shows increased tool count (was ~32, now ~37).

### Phase 2 Checkpoint

```bash
# Lint
uv run ruff check src/obsidian_brain/tools/session.py

# Type check (if mypy configured)
uv run mypy src/obsidian_brain/tools/session.py --ignore-missing-imports

# Test server starts
timeout 5 uv run python -m obsidian_brain.server 2>&1 || true
# Should not crash on import

# Test individual tool imports
uv run python -c "
from obsidian_brain.tools.session import register_session_tools
print('Session tools module imports OK')
"
```

**Commit**: `feat: add session state management and MCP tools for plugin behaviors`

---

## Phase 3: Hook Scripts

**Goal**: Implement the three lifecycle hooks. These are standalone Python scripts invoked by Claude Code.

**Checkpoint**: Each script runs correctly when given mock stdin JSON.

**Depends on**: Phase 2 (brain-state.py module)

### Step 3.1 — Create session-start hook

**File**: `scripts/session-start.py` (NEW)

**Input**: stdin JSON with `session_id`, `cwd`, `hook_event_name`
**Output**: stdout JSON with `hookSpecificOutput.additionalContext`

**Logic**:
1. Parse stdin JSON
2. Read vault config via `brain_state.read_vault_config()`
3. Check `autonomy.session_start_context` — if `"disabled"`, exit 0 with no output
4. Read today's daily note via direct HTTP GET to `/periodic/daily/{Y}/{M}/{D}/`
5. Extract content under the configured daily_note_heading
6. Initialize session state via `brain_state.write_state()`
7. Output context summary JSON

**Performance target**: < 2 seconds

**Verification**:
```bash
echo '{"session_id":"test123","cwd":"/tmp","hook_event_name":"SessionStart"}' | \
  OBSIDIAN_API_KEY=your-key python3 scripts/session-start.py
# Should output JSON with additionalContext (or gracefully handle missing vault)
```

### Step 3.2 — Create periodic check-in hook

**File**: `scripts/periodic-checkin.py` (NEW)

**Input**: stdin JSON with `session_id`, `hook_event_name`
**Output**: stdout JSON (or empty for no-op)

**Logic**:
1. Parse stdin JSON
2. Read session state via `brain_state.read_state()`
3. Read vault config for `checkin_interval_minutes` and `autonomy.periodic_checkin`
4. If disabled: exit 0
5. Calculate elapsed time since `last_checkin`
6. If elapsed < interval: exit 0 (no output — this is the common fast path)
7. If elapsed >= interval: update `last_checkin`, output check-in prompt JSON

**Performance target**: < 500ms (file I/O only when interval not reached)

**Verification**:
```bash
# First call: initializes state, no check-in yet (interval not reached)
echo '{"session_id":"test456","hook_event_name":"Stop"}' | \
  python3 scripts/periodic-checkin.py
# Should output nothing (exit 0, no stdout)

# Modify state file to set last_checkin 31 minutes ago, run again
# Should output check-in prompt JSON
```

### Step 3.3 — Populate hooks.json with full configuration

**File**: `hooks/hooks.json` (MODIFY — replace placeholder from Phase 1)

```json
{
  "description": "Obsidian Brain lifecycle hooks for session tracking and knowledge capture",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/session-start.py",
            "timeout": 5000,
            "statusMessage": "Loading vault context..."
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/periodic-checkin.py",
            "timeout": 3000
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Evaluate if this session contained noteworthy learnings, decisions, or accomplishments worth capturing in Obsidian. Noteworthy: bugs fixed, concepts learned, features built, decisions made. NOT noteworthy: simple questions, trivial edits, casual chat. If noteworthy, briefly describe what to capture. If not, respond: nothing noteworthy",
            "model": "claude-haiku-4-5-20251001",
            "timeout": 10000
          }
        ]
      }
    ]
  }
}
```

**Verification**: Valid JSON. Scripts exist at referenced paths (relative to plugin root).

### Phase 3 Checkpoint

```bash
# Verify all scripts are executable
python3 scripts/session-start.py <<< '{"session_id":"test","hook_event_name":"SessionStart"}'
python3 scripts/periodic-checkin.py <<< '{"session_id":"test","hook_event_name":"Stop"}'

# Verify hooks.json is valid
python3 -c "import json; json.load(open('hooks/hooks.json')); print('Valid')"

# Lint scripts
uv run ruff check scripts/
```

**Commit**: `feat: add lifecycle hooks for session start, periodic check-in, and session-end evaluation`

---

## Phase 4: Skills

**Goal**: Create the 5 SKILL.md files that define user-facing slash commands.

**Checkpoint**: Each skill is loadable via `claude --plugin-dir . --help` and appears in the `/` menu.

**Depends on**: Phase 2 (MCP tools referenced by skills)

**Independent of**: Phase 3 (hooks and skills don't depend on each other)

### Step 4.1 — /document-it skill

**File**: `skills/document-it/SKILL.md` (NEW)

**Frontmatter**:
```yaml
---
name: document-it
description: Document the current context — a function, file, decision, or concept — as a structured Obsidian note
argument-hint: "[what to document]"
user-invocable: true
allowed-tools:
  - mcp__obsidian-brain__get_brain_config
  - mcp__obsidian-brain__get_vault_config
  - mcp__obsidian-brain__search_content
  - mcp__obsidian-brain__create_note
  - mcp__obsidian-brain__list_all_tags
  - mcp__obsidian-brain__record_session_activity
  - mcp__obsidian-brain__create_daily_entry
---
```

**Body**: Detailed instructions for Claude covering:
- Purpose and when to use
- Step-by-step workflow (config → search → compose → create → track → log)
- Note output format template (frontmatter, heading structure, wikilinks)
- Convention rules (use vault naming patterns, tag from taxonomy, place in correct folder)
- Examples of different document types (function doc, decision record, concept note)

### Step 4.2 — /capture-learning skill

**File**: `skills/capture-learning/SKILL.md` (NEW)

**Frontmatter**:
```yaml
---
name: capture-learning
description: Capture what was learned during this session as a structured learning note
argument-hint: "[optional focus area]"
user-invocable: true
allowed-tools:
  - mcp__obsidian-brain__get_brain_config
  - mcp__obsidian-brain__get_vault_config
  - mcp__obsidian-brain__search_content
  - mcp__obsidian-brain__create_note
  - mcp__obsidian-brain__list_all_tags
  - mcp__obsidian-brain__record_session_activity
  - mcp__obsidian-brain__create_daily_entry
  - mcp__obsidian-brain__append_to_brag_doc
  - mcp__obsidian-brain__get_session_state
---
```

**Body**: Instructions for Claude covering:
- Analyze session transcript for key learnings
- If `$ARGUMENTS` provided, focus analysis on that topic
- Learning note structure: Context, What I Learned, Why It Matters, Related
- Tag with topic-relevant tags from vault taxonomy
- Daily note entry with wikilink to learning note
- Brag doc integration (check autonomy config first)

### Step 4.3 — /review-session skill

**File**: `skills/review-session/SKILL.md` (NEW)

**Frontmatter**:
```yaml
---
name: review-session
description: Generate a session review — summarize what was done, decisions made, issues resolved
user-invocable: true
allowed-tools:
  - mcp__obsidian-brain__get_brain_config
  - mcp__obsidian-brain__get_vault_config
  - mcp__obsidian-brain__get_session_state
  - mcp__obsidian-brain__search_content
  - mcp__obsidian-brain__append_to_daily
  - mcp__obsidian-brain__create_daily_entry
  - mcp__obsidian-brain__record_session_activity
  - mcp__obsidian-brain__append_to_brag_doc
---
```

**Body**: Instructions for Claude covering:
- Check session state for what's already logged (dedup)
- Analyze full transcript for activities, decisions, outcomes
- Generate high-level summary (2-3 lines with timestamps)
- Daily note entry format: `- [HH:MM] Summary [[Created Notes]]`
- Brag doc entries for accomplishments (respecting autonomy)
- Include wikilinks to all notes created during session

### Step 4.4 — /brain-status skill

**File**: `skills/brain-status/SKILL.md` (NEW)

**Frontmatter**:
```yaml
---
name: brain-status
description: Show the current state of the Obsidian Brain integration
user-invocable: true
allowed-tools:
  - mcp__obsidian-brain__get_brain_config
  - mcp__obsidian-brain__check_onboarding_status
  - mcp__obsidian-brain__get_daily_note
  - mcp__obsidian-brain__get_session_state
  - mcp__obsidian-brain__list_memories
  - mcp__obsidian-brain__get_knowledge_base_status
---
```

**Body**: Instructions for Claude covering:
- Check vault connection and onboarding status
- Display today's daily note session log
- Show current session state (notes created, entries made)
- List recent memories with types
- Display autonomy configuration
- Format as a clean status report

### Step 4.5 — /brain-config skill

**File**: `skills/brain-config/SKILL.md` (NEW)

**Frontmatter**:
```yaml
---
name: brain-config
description: Configure Obsidian Brain autonomy levels and behavior preferences
argument-hint: "[setting] [value]"
user-invocable: true
allowed-tools:
  - mcp__obsidian-brain__get_brain_config
  - mcp__obsidian-brain__update_brain_config
---
```

**Body**: Instructions for Claude covering:
- If no arguments: display current config with explanations
- If arguments: parse setting name and value, validate, apply
- Available autonomy levels: `silent`, `prompt`, `disabled`
- Available settings and their meanings
- Confirmation of changes

### Phase 4 Checkpoint

```bash
# Verify all skill files exist
ls skills/document-it/SKILL.md
ls skills/capture-learning/SKILL.md
ls skills/review-session/SKILL.md
ls skills/brain-status/SKILL.md
ls skills/brain-config/SKILL.md

# Verify YAML frontmatter is valid in each
for f in skills/*/SKILL.md; do
  python3 -c "
import yaml
with open('$f') as fh:
    content = fh.read()
    if content.startswith('---'):
        fm = content.split('---', 2)[1]
        data = yaml.safe_load(fm)
        print(f'$f: name={data.get(\"name\")} invocable={data.get(\"user-invocable\")}')
"
done

# Test plugin loading with skills
claude --plugin-dir . --print-skills 2>&1 || echo "Skills check complete"
```

**Commit**: `feat: add 5 Obsidian Brain skills (/document-it, /capture-learning, /review-session, /brain-status, /brain-config)`

---

## Phase 5: Integration Testing & Polish

**Goal**: End-to-end validation, config system extension, documentation.

**Checkpoint**: Full plugin works when loaded via `claude --plugin-dir .`

### Step 5.1 — Extend onboarding config generation

**File**: `src/obsidian_brain/onboarding.py` (MODIFY)

Update `generate_config()` to include `autonomy` and `plugin` sections in the generated config YAML. Uses the defaults from the design doc. This ensures that when a user runs onboarding, they get the full config schema.

**Changes**:
- Add `autonomy` dict to the config output
- Add `plugin` dict to the config output
- Both use the defaults defined in the design doc

### Step 5.2 — Add tests for session tools

**File**: `tests/test_session_tools.py` (NEW)

Test the new session MCP tools in isolation:
- `get_brain_config` returns merged defaults when no vault config exists
- `update_brain_config` correctly updates dot-notation keys
- `get_session_state` returns defaults for unknown session
- `record_session_activity` adds to state and doesn't duplicate
- `append_to_brag_doc` creates brag doc if missing, appends under correct heading, deduplicates

### Step 5.3 — Add tests for hook scripts

**File**: `tests/test_hooks.py` (NEW)

Test hook scripts with mock stdin:
- `session-start.py` returns valid JSON with additionalContext
- `session-start.py` returns empty when autonomy is disabled
- `periodic-checkin.py` returns empty when interval not reached
- `periodic-checkin.py` returns check-in prompt when interval exceeded
- `periodic-checkin.py` returns empty when autonomy is disabled

### Step 5.4 — Update README

**File**: `README.md` (MODIFY)

Add sections:
- Plugin installation instructions
- Available skills and their usage
- Hook behaviors and what to expect
- Configuration guide (autonomy levels)
- Migration guide for existing standalone users

### Step 5.5 — Update server instructions

**File**: `src/obsidian_brain/server.py` (MODIFY)

Update the `instructions` string in the MCPServer constructor to document:
- New session tools
- Plugin integration context
- Brag doc management

### Phase 5 Checkpoint

```bash
# Run all tests
uv run pytest tests/ -v

# Lint everything
uv run ruff check src/ scripts/ tests/

# Verify full plugin loads
claude --plugin-dir . --print-config 2>&1 | head -20

# Manual smoke test: start a session with the plugin
claude --plugin-dir .
# Type /brain-status — should work
# Type /brain-config — should show defaults
```

**Commit**: `feat: complete plugin integration with tests, config extension, and documentation`

---

## Execution Order Diagram

```
                    Phase 1
                 Plugin Scaffold
               ┌───────────────┐
               │ plugin.json   │
               │ marketplace   │
               │ .mcp.json     │
               │ hooks stub    │
               └───────┬───────┘
                       │
                    Phase 2
              Session State & Tools
               ┌───────────────┐
               │ brain-state   │
               │ session.py    │
               │ server.py mod │
               └───────┬───────┘
                       │
              ┌────────┴────────┐
              │                 │
           Phase 3           Phase 4
         Hook Scripts         Skills
        ┌───────────┐    ┌───────────┐
        │ start.py  │    │ doc-it    │
        │ checkin   │    │ capture   │
        │ hooks.json│    │ review    │
        └─────┬─────┘    │ status    │
              │          │ config    │
              │          └─────┬─────┘
              │                │
              └────────┬───────┘
                       │
                    Phase 5
              Integration & Polish
               ┌───────────────┐
               │ onboarding    │
               │ tests         │
               │ README        │
               │ server docs   │
               └───────────────┘
```

---

## File Manifest

### New Files (16)

| # | File | Phase | Purpose |
|---|------|-------|---------|
| 1 | `.claude-plugin/plugin.json` | 1 | Plugin manifest |
| 2 | `.claude-plugin/marketplace.json` | 1 | Marketplace catalog |
| 3 | `hooks/hooks.json` | 1→3 | Hook event configuration |
| 4 | `scripts/brain-state.py` | 2 | Shared session state module |
| 5 | `src/obsidian_brain/tools/session.py` | 2 | Session tracking MCP tools |
| 6 | `scripts/session-start.py` | 3 | SessionStart hook script |
| 7 | `scripts/periodic-checkin.py` | 3 | Periodic check-in hook script |
| 8 | `skills/document-it/SKILL.md` | 4 | /document-it skill |
| 9 | `skills/capture-learning/SKILL.md` | 4 | /capture-learning skill |
| 10 | `skills/review-session/SKILL.md` | 4 | /review-session skill |
| 11 | `skills/brain-status/SKILL.md` | 4 | /brain-status skill |
| 12 | `skills/brain-config/SKILL.md` | 4 | /brain-config skill |
| 13 | `tests/test_session_tools.py` | 5 | Session tool tests |
| 14 | `tests/test_hooks.py` | 5 | Hook script tests |

### Modified Files (5)

| # | File | Phase | Change |
|---|------|-------|--------|
| 1 | `.mcp.json` | 1 | Use `uvx` with `${CLAUDE_PLUGIN_ROOT}` |
| 2 | `src/obsidian_brain/__init__.py` | 1 | Version bump to 0.2.0 |
| 3 | `pyproject.toml` | 1 | Version bump to 0.2.0 |
| 4 | `src/obsidian_brain/server.py` | 2, 5 | Register session tools + update instructions |
| 5 | `src/obsidian_brain/onboarding.py` | 5 | Add autonomy/plugin config to generated config |

### Unchanged Files

All existing tools (`vault.py`, `links.py`, `tags.py`, `search.py`, `daily.py`, `knowledge.py`, `memory.py`, `onboarding.py` tools), resources (`structure.py`, `knowledge.py`), utilities (`frontmatter.py`, `wikilinks.py`), core modules (`client.py`, `models.py`, `cache.py`, `knowledge.py`, `memory.py`) remain completely unchanged.

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|-----------|
| `uvx --from git+...` may not work for all users | Plugin MCP server won't start | Provide alternative local `.mcp.json` in README; detect and fall back |
| `${CLAUDE_PLUGIN_ROOT}` may not resolve in all contexts | Hook scripts fail to locate | Scripts check for env var and fall back to relative paths |
| Obsidian Local REST API not running | All vault operations fail | Session-start hook detects and reports "Brain offline" gracefully |
| Stop hook fires too frequently | Periodic check-in annoys user | Default interval is 30 min; first action in check-in script is time check (fast exit) |
| Brag doc auto-detection finds wrong note | Entries written to wrong place | `brain-managed: true` frontmatter tag identifies Brain-managed docs; `/brain-config` allows explicit path override |
| Session state temp file conflicts between concurrent sessions | State corruption | Each session gets unique temp file keyed by `session_id`; file locking prevents concurrent writes |

---

## Next Step

Use `/sc:implement` to begin executing this workflow phase by phase, starting with Phase 1 (Plugin Scaffold).
