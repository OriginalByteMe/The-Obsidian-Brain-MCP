# Do: Obsidian Brain Claude Code Plugin Transformation

**Started**: 2026-02-08
**Status**: In Progress

## Implementation Log (Chronological)

- **2026-02-08** Phase 1 started
- **2026-02-08** Phase 1 completed — plugin.json, marketplace.json, hooks stub, .mcp.json updated, version bumped to 0.2.0
- **2026-02-08** Phase 2 started
- **2026-02-08** Phase 2 completed — brain_state.py, session.py (5 MCP tools), server.py registration
- **2026-02-08** Phase 3 started
- **2026-02-08** Phase 3 completed — session-start.py, periodic-checkin.py, hooks.json populated (stdlib fallback for httpx)

---

## Phase 1: Plugin Scaffold

**Status**: Complete

### Task 1.1: Create plugin manifest

- [x] Create `.claude-plugin/plugin.json` with name, version 0.2.0, author, description
- [x] Verify: valid JSON, `name` field present

### Task 1.2: Create marketplace manifest

- [x] Create `.claude-plugin/marketplace.json` with plugin source pointing to "."
- [x] Verify: valid JSON, plugin entry resolves

### Task 1.3: Update MCP server configuration

- [x] Modify `.mcp.json` to use `uvx --from git+...` with `${OBSIDIAN_API_KEY}` env var
- [x] Verify: valid JSON

### Task 1.4: Create placeholder hooks.json

- [x] Create `hooks/hooks.json` with empty hooks object
- [x] Verify: valid JSON, referenced by plugin.json

### Task 1.5: Version bump

- [x] Update `src/obsidian_brain/__init__.py` from `"0.1.0"` to `"0.2.0"`
- [x] Update `pyproject.toml` version from `"0.1.0"` to `"0.2.0"`

### Phase 1 Verification

```bash
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"
python3 -c "import json; json.load(open('.claude-plugin/marketplace.json'))"
python3 -c "import json; json.load(open('.mcp.json'))"
python3 -c "import json; json.load(open('hooks/hooks.json'))"
uv run python -c "from obsidian_brain import __version__; assert __version__ == '0.2.0'"
```

**Commit**: `feat: add Claude Code plugin scaffold with manifests and marketplace config`

---

## Phase 2: Session State & Configuration Tools

**Status**: Complete

### Task 2.1: Create session state manager

- [x] Create `scripts/brain_state.py` (renamed from brain-state.py for Python import compatibility) with:
  - `get_state_path(session_id)` — temp file path
  - `read_state(session_id)` — atomic read with defaults
  - `write_state(session_id, state)` — atomic write with file locking
  - `read_vault_config()` — direct HTTP config read
  - `DEFAULT_AUTONOMY` and `DEFAULT_PLUGIN` constants
- [x] Verify: module imports and returns default state

### Task 2.2: Create session MCP tools

- [x] Create `src/obsidian_brain/tools/session.py` with `register_session_tools()`:
  - `get_brain_config()` — reads config, merges with defaults
  - `update_brain_config(key, value)` — dot-notation config update
  - `get_session_state()` — reads session tracking state
  - `record_session_activity(activity_type, summary, note_paths)` — tracks activity + optional daily note
  - `append_to_brag_doc(category, description, links)` — dedup + append to brag doc
- [x] Verify: module imports cleanly, ruff passes

### Task 2.3: Register session tools in server

- [x] Add import in `server.py`: `from .tools.session import register_session_tools`
- [x] Add registration: `register_session_tools(server)` after existing registrations
- [x] Verify: server imports without error

### Phase 2 Verification

```bash
uv run ruff check src/obsidian_brain/tools/session.py
uv run python -c "from obsidian_brain.server import server; print('Server OK')"
```

**Commit**: `feat: add session state management and MCP tools for plugin behaviors`

---

## Phase 3: Hook Scripts

**Status**: Complete

### Task 3.1: Create session-start hook

- [x] Create `scripts/session-start.py`:
  - Parse stdin JSON for `session_id`
  - Read vault config via `brain_state.read_vault_config()` (with stdlib fallback)
  - Check `autonomy.session_start_context` — exit if disabled
  - Read today's daily note via stdlib urllib (no httpx dependency)
  - Initialize session state temp file
  - Output JSON with `additionalContext`
- [x] Verify with mock input: outputs valid JSON

### Task 3.2: Create periodic check-in hook

- [x] Create `scripts/periodic-checkin.py`:
  - Parse stdin JSON for `session_id`
  - Read session state for `last_checkin` timestamp
  - Read config for `checkin_interval_minutes` and autonomy setting
  - If disabled or interval not reached: exit 0 (no output)
  - If interval reached: update `last_checkin`, output check-in prompt JSON
- [x] Verify with mock input: exits silently when interval not reached

### Task 3.3: Populate hooks.json

- [x] Replace stub `hooks/hooks.json` with full configuration:
  - `SessionStart` → `session-start.py` (command type, 5s timeout)
  - `Stop[0]` → `periodic-checkin.py` (command type, 3s timeout)
  - `Stop[1]` → session-end prompt (prompt type, Haiku model, 10s timeout)
- [x] Verify: valid JSON, script paths use `${CLAUDE_PLUGIN_ROOT}`

### Phase 3 Verification

```bash
python3 -c "import json; d=json.load(open('hooks/hooks.json')); print(f'{len(d[\"hooks\"])} hook events')"
echo '{"session_id":"t","hook_event_name":"SessionStart"}' | python3 scripts/session-start.py 2>/dev/null; echo "Exit: $?"
echo '{"session_id":"t","hook_event_name":"Stop"}' | python3 scripts/periodic-checkin.py 2>/dev/null; echo "Exit: $?"
```

**Commit**: `feat: add lifecycle hooks for session start, periodic check-in, and session-end evaluation`

---

## Phase 4: Skills

**Status**: Not Started

### Task 4.1: Create /document-it skill

- [ ] Create `skills/document-it/SKILL.md` with:
  - Frontmatter: name, description, argument-hint, user-invocable, allowed-tools
  - Body: purpose, prerequisites (config + conventions), workflow (6 steps), output format, convention rules
- [ ] Verify: valid YAML frontmatter

### Task 4.2: Create /capture-learning skill

- [ ] Create `skills/capture-learning/SKILL.md` with:
  - Frontmatter: name, description, argument-hint, user-invocable, allowed-tools
  - Body: transcript analysis, learning note structure (Context/What/Why/Related), daily note + brag doc integration
- [ ] Verify: valid YAML frontmatter

### Task 4.3: Create /review-session skill

- [ ] Create `skills/review-session/SKILL.md` with:
  - Frontmatter: name, description, user-invocable, allowed-tools
  - Body: session state check, transcript analysis, daily note summary format, brag doc integration
- [ ] Verify: valid YAML frontmatter

### Task 4.4: Create /brain-status skill

- [ ] Create `skills/brain-status/SKILL.md` with:
  - Frontmatter: name, description, user-invocable, allowed-tools
  - Body: vault check, daily note summary, session state, memories, config display
- [ ] Verify: valid YAML frontmatter

### Task 4.5: Create /brain-config skill

- [ ] Create `skills/brain-config/SKILL.md` with:
  - Frontmatter: name, description, argument-hint, user-invocable, allowed-tools
  - Body: display current config, parse arguments, validate values, apply changes
- [ ] Verify: valid YAML frontmatter

### Phase 4 Verification

```bash
for f in skills/*/SKILL.md; do
  python3 -c "
import yaml
content = open('$f').read()
fm = content.split('---', 2)[1]
data = yaml.safe_load(fm)
print(f'$f: name={data[\"name\"]} invocable={data[\"user-invocable\"]}')
"
done
```

**Commit**: `feat: add 5 Obsidian Brain skills (/document-it, /capture-learning, /review-session, /brain-status, /brain-config)`

---

## Phase 5: Integration Testing & Polish

**Status**: Not Started

### Task 5.1: Extend onboarding config

- [ ] Modify `src/obsidian_brain/onboarding.py`:
  - Update `generate_config()` to include `autonomy` section with defaults
  - Update `generate_config()` to include `plugin` section with defaults
- [ ] Verify: generated YAML includes both new sections

### Task 5.2: Add session tool tests

- [ ] Create `tests/test_session_tools.py`:
  - Test `get_brain_config` returns merged defaults
  - Test `update_brain_config` handles dot-notation keys
  - Test `get_session_state` returns defaults for new session
  - Test `record_session_activity` tracks without duplicates
  - Test `append_to_brag_doc` creates doc, appends, and deduplicates
- [ ] Verify: all tests pass

### Task 5.3: Add hook script tests

- [ ] Create `tests/test_hooks.py`:
  - Test `session-start.py` outputs valid JSON
  - Test `session-start.py` respects disabled autonomy
  - Test `periodic-checkin.py` returns empty when interval not reached
  - Test `periodic-checkin.py` returns prompt when interval exceeded
  - Test `periodic-checkin.py` respects disabled autonomy
- [ ] Verify: all tests pass

### Task 5.4: Update server instructions

- [ ] Modify `src/obsidian_brain/server.py` instructions to document:
  - New session tools (5)
  - Plugin context (available skills and hooks)
  - Brag doc management
- [ ] Verify: server starts with updated instructions

### Task 5.5: Update README

- [ ] Add "Plugin Installation" section to `README.md`
- [ ] Add "Available Skills" section with usage examples
- [ ] Add "Lifecycle Hooks" section describing automated behaviors
- [ ] Add "Configuration" section explaining autonomy levels
- [ ] Verify: README renders correctly

### Phase 5 Verification

```bash
uv run pytest tests/ -v
uv run ruff check src/ scripts/ tests/
```

**Commit**: `feat: complete plugin integration with tests, config extension, and documentation`

---

## Learnings During Implementation

1. Hook scripts run as subprocesses outside the UV venv — cannot depend on httpx/yaml. Added stdlib urllib fallback in brain_state.py and session-start.py.
2. Python module filenames must use underscores, not hyphens. Renamed `brain-state.py` → `brain_state.py`.

---

## Errors Encountered

| Timestamp | Error | Root Cause | Solution |
|-----------|-------|------------|----------|
| | | | |
