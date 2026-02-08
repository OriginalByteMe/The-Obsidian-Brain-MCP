# Obsidian Brain — Plugin Architecture Design

> **Status**: Architecture Design
> **Date**: 2026-02-05
> **Input**: [brainstorm-plugin-requirements.md](./brainstorm-plugin-requirements.md)
> **Next Step**: `/sc:workflow` for phased implementation plan

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Repository Layout](#2-repository-layout)
3. [Plugin Manifest & Distribution](#3-plugin-manifest--distribution)
4. [MCP Server Integration](#4-mcp-server-integration)
5. [Skills Architecture](#5-skills-architecture)
6. [Hooks Architecture](#6-hooks-architecture)
7. [Session State Management](#7-session-state-management)
8. [Configuration System](#8-configuration-system)
9. [Data Flow Diagrams](#9-data-flow-diagrams)
10. [Skill Specifications](#10-skill-specifications)
11. [Hook Specifications](#11-hook-specifications)
12. [Brag Doc Engine](#12-brag-doc-engine)
13. [Open Question Resolutions](#13-open-question-resolutions)
14. [Migration Strategy](#14-migration-strategy)

---

## 1. Architecture Overview

### Design Philosophy

The plugin follows a **layered architecture** where each layer has a clear responsibility:

```
┌─────────────────────────────────────────────────────────┐
│                    Claude Code CLI                        │
│              (host — runs skills, hooks)                  │
├─────────────────────────────────────────────────────────┤
│  SKILLS LAYER          │  HOOKS LAYER                    │
│  (/document-it, etc.)  │  (SessionStart, Stop, etc.)     │
│  SKILL.md files that   │  hooks.json + scripts/ that     │
│  instruct Claude how   │  run at lifecycle events         │
│  to use MCP tools      │                                 │
├────────────────────────┴────────────────────────────────┤
│                  SESSION STATE LAYER                      │
│          (scripts/brain-state.py — shared state)          │
│          Tracks: created notes, entries, timestamps       │
├─────────────────────────────────────────────────────────┤
│                    MCP TOOLS LAYER                        │
│              (obsidian-brain MCP server)                  │
│           32 existing tools + new tools                   │
├─────────────────────────────────────────────────────────┤
│                 OBSIDIAN LOCAL REST API                   │
│               (Obsidian plugin — port 27124)              │
└─────────────────────────────────────────────────────────┘
```

**Key insight**: Skills are *instructions to Claude*, not code. They tell Claude which MCP tools to call, in what order, and with what conventions. The MCP server does the actual vault work. Hook scripts are lightweight shell/Python scripts that provide context or check conditions — they don't do heavy vault operations themselves.

### Component Interaction Model

```
User types /document-it auth flow
        │
        ▼
┌──────────────────┐
│  Claude Code CLI  │──── loads SKILL.md instructions
│                   │──── Claude reads vault config via MCP
│                   │──── Claude searches vault via MCP
│                   │──── Claude creates note via MCP
│                   │──── Claude updates daily note via MCP
│                   │──── Claude updates session state via MCP
└──────────────────┘
        │
        ▼
┌──────────────────┐
│  MCP Server       │──── obsidian-brain (existing + new tools)
│  (stdio)          │
└──────────────────┘
        │
        ▼
┌──────────────────┐
│  Obsidian API     │──── Local REST API (port 27124)
└──────────────────┘
```

---

## 2. Repository Layout

The existing repo is restructured to be both a **development repo** and a **plugin distribution**:

```
The-Obsidian-Brain-MCP/              # Root = plugin root
│
├── .claude-plugin/
│   └── plugin.json                  # NEW — plugin manifest
│
├── .mcp.json                        # MODIFIED — uses ${CLAUDE_PLUGIN_ROOT}
│
├── skills/                          # NEW — skill definitions
│   ├── document-it/
│   │   └── SKILL.md
│   ├── capture-learning/
│   │   └── SKILL.md
│   ├── review-session/
│   │   └── SKILL.md
│   ├── brain-status/
│   │   └── SKILL.md
│   └── brain-config/
│       └── SKILL.md
│
├── hooks/
│   └── hooks.json                   # NEW — hook event configuration
│
├── scripts/                         # NEW — hook implementation scripts
│   ├── session-start.py             # SessionStart hook
│   ├── session-end-check.py         # Stop hook (session end evaluation)
│   ├── periodic-checkin.py          # Stop hook (time-based check-in)
│   └── brain-state.py              # Shared session state management
│
├── src/
│   └── obsidian_brain/              # EXISTING — MCP server (unchanged core)
│       ├── server.py
│       ├── client.py
│       ├── models.py
│       ├── cache.py
│       ├── knowledge.py
│       ├── memory.py
│       ├── onboarding.py
│       ├── tools/
│       │   ├── vault.py
│       │   ├── links.py
│       │   ├── tags.py
│       │   ├── search.py
│       │   ├── daily.py
│       │   ├── knowledge.py
│       │   ├── memory.py
│       │   ├── onboarding.py
│       │   └── session.py           # NEW — session tracking tools
│       ├── resources/
│       │   ├── structure.py
│       │   └── knowledge.py
│       └── utils/
│           ├── frontmatter.py
│           └── wikilinks.py
│
├── docs/                            # Design docs (not distributed)
├── tests/                           # Tests (not distributed)
├── pyproject.toml                   # Python package config
├── README.md
└── LICENSE
```

### What's New vs. Existing

| Component | Status | Purpose |
|-----------|--------|---------|
| `.claude-plugin/plugin.json` | **New** | Plugin manifest for Claude Code |
| `.mcp.json` | **Modified** | Portable MCP config with `${CLAUDE_PLUGIN_ROOT}` |
| `skills/` | **New** | 5 skill definitions (SKILL.md files) |
| `hooks/hooks.json` | **New** | Hook event configuration |
| `scripts/` | **New** | 4 Python scripts for hooks and state |
| `src/obsidian_brain/tools/session.py` | **New** | Session tracking MCP tools |
| Everything else in `src/` | **Existing** | Unchanged MCP server |

---

## 3. Plugin Manifest & Distribution

### plugin.json

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

**Design decisions**:
- `skills/` is auto-discovered from the default directory (no explicit path needed in manifest)
- `mcpServers` and `hooks` explicitly point to their configs
- Version bumped to 0.2.0 to reflect the plugin transformation

### Distribution Model

**Primary**: Marketplace in this repo (self-contained)

```
The-Obsidian-Brain-MCP/
├── .claude-plugin/
│   ├── plugin.json          # This IS the plugin
│   └── marketplace.json     # This IS the marketplace
└── ...
```

**marketplace.json**:
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

**Installation flow**:
```bash
# Add the marketplace
/plugin marketplace add OriginalByteMe/The-Obsidian-Brain-MCP

# Install the plugin
/plugin install obsidian-brain@obsidian-brain-marketplace
```

### Python Dependency Handling

The MCP server requires Python 3.12+ and UV. The `.mcp.json` uses `uvx` which handles the Python environment:

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

**Why `uvx` from git**: Plugin files are copied to a cache directory (`${CLAUDE_PLUGIN_ROOT}`), but the Python virtual environment and dependencies need proper installation. Using `uvx --from git+...` means:
1. UV installs the package from GitHub into an isolated environment
2. No dependency on the plugin's local copy having a `.venv`
3. Users just need `uv` installed (standard for Python developers)

**Alternative for local development**:
```json
{
  "mcpServers": {
    "obsidian-brain": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run", "--directory", "${CLAUDE_PLUGIN_ROOT}",
        "--env-file", "${CLAUDE_PLUGIN_ROOT}/.env",
        "python", "-m", "obsidian_brain.server"
      ]
    }
  }
}
```

---

## 4. MCP Server Integration

### New Tool: Session Tracking

A new tool module `src/obsidian_brain/tools/session.py` provides session state management accessible to both skills and hooks.

```python
# tools/session.py — Session tracking tools

def register_session_tools(server: "MCPServer") -> None:
    """Register session tracking tools."""

    @server.tool()
    async def get_brain_config() -> str:
        """
        Get the current Obsidian Brain plugin configuration.

        Returns the autonomy settings, daily note heading, brag doc path,
        and other plugin preferences from .obsidian-brain/config.yml.
        """

    @server.tool()
    async def update_brain_config(key: str, value: str) -> str:
        """
        Update a specific plugin configuration value.

        Args:
            key: Dot-notation config key (e.g., "autonomy.brag_doc_update")
            value: New value (e.g., "silent", "prompt", "disabled")
        """

    @server.tool()
    async def get_session_state() -> str:
        """
        Get the current session tracking state.

        Returns: notes created this session, daily note entries made,
        last check-in time, session start time.
        """

    @server.tool()
    async def record_session_activity(
        activity_type: str,
        summary: str,
        note_paths: list[str] | None = None,
    ) -> str:
        """
        Record an activity in the session state and optionally in the daily note.

        Args:
            activity_type: Type of activity (note_created, learning_captured,
                          session_reviewed, brag_updated)
            summary: Brief description of what happened
            note_paths: Paths of notes created/modified
        """

    @server.tool()
    async def append_to_brag_doc(
        category: str,
        description: str,
        links: list[str] | None = None,
    ) -> str:
        """
        Add an entry to the brag document.

        Args:
            category: One of "Features Built", "Bugs Fixed",
                     "Improvements", "Key Learnings"
            description: Brief description of the accomplishment
            links: Optional note names to wikilink
        """
```

### Server Registration Update

```python
# server.py additions
from .tools.session import register_session_tools

# After existing registrations:
register_session_tools(server)
```

### Why New MCP Tools (Not Just Skills)

Skills instruct Claude *what to do*, but they need MCP tools to *do it*. The new session tools give Claude:

1. **`get_brain_config`** — Read autonomy preferences so skills respect user settings
2. **`update_brain_config`** — `/brain-config` skill uses this to change settings
3. **`get_session_state`** — Deduplication — know what's already been logged
4. **`record_session_activity`** — Atomic tracking of what happened this session
5. **`append_to_brag_doc`** — Structured brag doc updates with dedup checking

The existing tools (`append_to_daily`, `create_daily_entry`, `create_note`, `search_content`, `get_vault_config`, etc.) remain unchanged and are reused by skills.

---

## 5. Skills Architecture

### Design Principles

1. **Skills are instructions, not code** — They tell Claude which MCP tools to use and in what order
2. **Skills use existing MCP tools** — No logic duplication between skills and the server
3. **Skills respect autonomy** — Every skill reads `get_brain_config` before taking action
4. **Skills are context-aware** — They reference the transcript, vault conventions, and session state

### Skill Communication Pattern

```
┌────────────────────────┐
│  User: /document-it X  │
└──────────┬─────────────┘
           ▼
┌────────────────────────┐
│  Claude loads SKILL.md │ ← Instructions, not code
│  instructions          │
└──────────┬─────────────┘
           ▼
┌────────────────────────────────────────┐
│  Claude follows instructions:          │
│  1. get_brain_config → read prefs      │
│  2. get_vault_config → read conventions│
│  3. search_content → find related notes│
│  4. create_note → create the doc note  │
│  5. record_session_activity → track it │
│  6. append_to_daily → log in daily     │
└────────────────────────────────────────┘
```

### SKILL.md Template Pattern

All skills share a common structure:

```yaml
---
name: skill-name
description: When Claude should use this skill
user-invocable: true
allowed-tools:
  - mcp__obsidian-brain__get_brain_config
  - mcp__obsidian-brain__get_vault_config
  - mcp__obsidian-brain__search_content
  # ... skill-specific tools
---

## Purpose
What this skill does.

## Prerequisites
1. Call `get_brain_config` to load autonomy preferences
2. Call `get_vault_config` to load vault conventions

## Workflow
Step-by-step instructions for Claude.

## Output Format
What the generated note/entry should look like.

## Conventions
Rules about tagging, naming, linking.
```

---

## 6. Hooks Architecture

### Hook Event Mapping

```
┌─────────────────────────────────────────────────────────────┐
│                       Hook Events                            │
├─────────────────┬────────────────┬──────────────────────────┤
│  SessionStart   │  Stop          │  Stop (periodic)         │
│                 │  (session end) │  (time-based check-in)   │
├─────────────────┼────────────────┼──────────────────────────┤
│  Type: command  │  Type: prompt  │  Type: command            │
│  Script:        │  Model: haiku  │  Script:                  │
│  session-       │  Evaluates if  │  periodic-                │
│  start.py       │  session was   │  checkin.py               │
│                 │  noteworthy    │                            │
├─────────────────┼────────────────┼──────────────────────────┤
│  Output:        │  Output:       │  Output:                  │
│  additionalCon- │  additionalCon-│  additionalContext with   │
│  text with      │  text with     │  check-in prompt OR       │
│  today's context│  capture prompt│  empty (skip)             │
└─────────────────┴────────────────┴──────────────────────────┘
```

### Hook Implementation Strategy

**Session Start** (`command` type):
- Reads today's daily note via Obsidian API directly (lightweight HTTP call)
- Reads `.obsidian-brain/config.yml` for preferences
- Returns `additionalContext` with today's summary for Claude's awareness

**Session End** (`prompt` type):
- Uses a fast Haiku model to evaluate the transcript
- Checks if learning capture is warranted
- Returns guidance text that Claude presents to the user

**Periodic Check-in** (`command` type):
- Tracks timestamps in a temp file (`/tmp/obsidian-brain-checkin-{session_id}`)
- Compares elapsed time against configured interval
- Returns empty output (no-op) if not enough time has passed
- Returns gentle check-in prompt if interval exceeded

### hooks.json Structure

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
            "prompt": "Evaluate if this session contained noteworthy learnings, decisions, or accomplishments that should be captured. Consider: Was a bug fixed? Was something new learned? Was a significant feature built? Was a difficult decision made? If YES, respond with a brief suggestion of what to capture. If NO (just casual questions, small edits, or trivial tasks), respond with 'nothing noteworthy'. Be concise.",
            "model": "claude-haiku-4-5-20251001",
            "timeout": 10000
          }
        ]
      }
    ]
  }
}
```

**Design note**: Two separate `Stop` hook entries run in sequence. The periodic check-in runs first (fast, usually no-op). The session-end evaluator runs second. This avoids both competing on the same response.

---

## 7. Session State Management

### State Architecture

Session state is ephemeral (lives for one Claude Code session) and tracks what the plugin has done to prevent duplication.

```
┌──────────────────────────────────────────────┐
│           Session State (in-memory)           │
│                                               │
│  session_id: "abc123"                         │
│  started_at: "2026-02-05T09:30:00"           │
│  last_checkin: "2026-02-05T10:00:00"         │
│                                               │
│  notes_created: [                             │
│    "Learning/Race Conditions.md",             │
│    "Projects/Auth Cache Fix.md"               │
│  ]                                            │
│                                               │
│  daily_entries: [                             │
│    "[09:30] Started debugging auth cache...", │
│    "[10:15] Created learning note..."         │
│  ]                                            │
│                                               │
│  brag_entries: [                              │
│    "Fixed auth race condition"                │
│  ]                                            │
│                                               │
│  autonomy_config: {                           │
│    session_start_context: "silent",           │
│    session_end_learning_capture: "prompt",    │
│    ...                                        │
│  }                                            │
└──────────────────────────────────────────────┘
```

### State Storage Mechanism

Hook scripts and MCP tools need shared state within a session. The approach:

**For hook scripts** (run as subprocesses):
- State stored in a temp file: `/tmp/obsidian-brain-{session_id}.json`
- `session_id` comes from the hook input JSON's `session_id` field
- Scripts read/write this JSON atomically (file locking)

**For MCP tools** (run in the server process):
- In-memory dict keyed by session concept (reset on server restart)
- MCP tools expose `get_session_state` and `record_session_activity`
- The session tools read the same temp file for cross-process coordination

**For skills** (instructions to Claude):
- Skills call `get_session_state` MCP tool to check for duplicates
- Skills call `record_session_activity` after creating notes/entries

### scripts/brain-state.py

Shared Python module for state management, used by all hook scripts:

```python
"""
Session state management for Obsidian Brain hooks.

Provides atomic read/write of session state stored in temp files.
Used by hook scripts to coordinate state across the session lifecycle.
"""

import json
import os
import fcntl
from pathlib import Path
from datetime import datetime

STATE_DIR = Path("/tmp")

def get_state_path(session_id: str) -> Path:
    return STATE_DIR / f"obsidian-brain-{session_id}.json"

def read_state(session_id: str) -> dict:
    path = get_state_path(session_id)
    if not path.exists():
        return {
            "session_id": session_id,
            "started_at": datetime.now().isoformat(),
            "last_checkin": datetime.now().isoformat(),
            "notes_created": [],
            "daily_entries": [],
            "brag_entries": [],
        }
    with open(path, "r") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        data = json.load(f)
        fcntl.flock(f, fcntl.LOCK_UN)
    return data

def write_state(session_id: str, state: dict) -> None:
    path = get_state_path(session_id)
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(state, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)

def read_config(vault_api_key: str, vault_host: str = "127.0.0.1",
                vault_port: int = 27124) -> dict:
    """Read .obsidian-brain/config.yml from vault via API."""
    import httpx
    url = f"https://{vault_host}:{vault_port}/vault/Obsidian Brain/config.yml"
    headers = {
        "Authorization": f"Bearer {vault_api_key}",
        "Accept": "text/markdown",
    }
    try:
        resp = httpx.get(url, headers=headers, verify=False, timeout=3.0)
        if resp.status_code == 200:
            import yaml
            return yaml.safe_load(resp.text) or {}
    except Exception:
        pass
    return {}
```

---

## 8. Configuration System

### Config Schema

The existing `.obsidian-brain/config.yml` (in the vault) is extended with an `autonomy` section:

```yaml
# Existing config (from onboarding)
version: "1.0"
created: "2026-02-05T..."
vault_profile:
  organizational_systems: ["PARA Method"]
  folder_purposes:
    projects: "Active projects with deadlines"
    areas: "Ongoing areas of responsibility"
    resources: "Reference materials"
    archive: "Inactive items"
  depth_levels: 4
conventions:
  tag_prefixes: ["status", "type", "project"]
  naming_patterns: ["Title Case naming"]
  # ...

# NEW — Plugin autonomy settings
autonomy:
  session_start_context: silent        # silent | prompt | disabled
  session_end_learning_capture: prompt # silent | prompt | disabled
  session_end_daily_log: silent        # silent | prompt | disabled
  brag_doc_update: prompt              # silent | prompt | disabled
  periodic_checkin: prompt             # silent | prompt | disabled

# NEW — Plugin behavior settings
plugin:
  checkin_interval_minutes: 30
  daily_note_heading: "## Claude Code Sessions"
  brag_doc_path: null                  # null = auto-detect, or explicit path
  brag_doc_categories:
    - "Features Built"
    - "Bugs Fixed"
    - "Improvements"
    - "Key Learnings"
  learning_note_folder: null           # null = follows vault conventions
  session_log_format: "summary"        # summary | structured
```

### Config Defaults

When no config exists yet (pre-onboarding), the plugin uses these hardcoded defaults:

```python
DEFAULT_CONFIG = {
    "autonomy": {
        "session_start_context": "silent",
        "session_end_learning_capture": "prompt",
        "session_end_daily_log": "silent",
        "brag_doc_update": "prompt",
        "periodic_checkin": "prompt",
    },
    "plugin": {
        "checkin_interval_minutes": 30,
        "daily_note_heading": "## Claude Code Sessions",
        "brag_doc_path": None,
        "brag_doc_categories": [
            "Features Built", "Bugs Fixed", "Improvements", "Key Learnings"
        ],
        "learning_note_folder": None,
        "session_log_format": "summary",
    },
}
```

### Config Access Pattern

```
Hooks (scripts/)              Skills (SKILL.md)
     │                              │
     │ read_config()                │ get_brain_config (MCP tool)
     │ (direct HTTP to API)         │ (via MCP server)
     ▼                              ▼
┌────────────────────────────────────────┐
│     .obsidian-brain/config.yml         │
│     (in Obsidian vault)                │
└────────────────────────────────────────┘
```

Hook scripts read config directly via the Obsidian REST API (lightweight, fast). Skills read config via the `get_brain_config` MCP tool (which does the same internally but through the MCP protocol).

---

## 9. Data Flow Diagrams

### Session Lifecycle Flow

```
SESSION START
─────────────
  SessionStart hook fires
      │
      ▼
  session-start.py runs:
  ├── Read .obsidian-brain/config.yml → load autonomy prefs
  ├── Read today's daily note → extract session log section
  ├── Initialize session state temp file
  └── Return additionalContext:
      "🧠 Brain connected. Today: [summary of 2 prior sessions]"
      │
      ▼
  Claude has vault context in its system prompt

DURING SESSION
──────────────
  User works normally. When a Stop event fires:
      │
      ▼
  periodic-checkin.py runs:
  ├── Read session state → check last_checkin timestamp
  ├── If elapsed < interval → exit 0 (no output, skip)
  └── If elapsed >= interval → return additionalContext:
      "It's been a while — anything worth noting down?"
      │
      ▼
  If user says yes → Claude uses MCP tools to capture
  If user says no → periodic-checkin.py resets timer

SESSION END (Stop hook, prompt type)
─────────────
  Haiku evaluates transcript:
  ├── If noteworthy → returns: "This session had [learnings/fixes].
  │   Consider running /capture-learning or /review-session."
  └── If trivial → returns: "nothing noteworthy"
      │
      ▼
  Claude presents recommendation to user:
  ├── User picks /capture-learning → skill runs
  ├── User picks /review-session → skill runs
  ├── User picks "Just log it" → Claude calls append_to_daily
  └── User picks "Skip" → nothing happens
```

### Note Creation Flow (used by all skills)

```
  Skill instruction says: "Create a note about X"
      │
      ▼
  1. get_brain_config
     └── Returns autonomy level + conventions
      │
      ▼
  2. get_vault_config
     └── Returns vault patterns (PARA, naming, tags)
      │
      ▼
  3. search_content("related topic keywords")
     └── Returns related existing notes for linking
      │
      ▼
  4. Claude composes note content:
     ├── Frontmatter with convention-appropriate keys
     ├── Content structured per skill's output format
     ├── Wikilinks to related notes from step 3
     └── Tags from vault taxonomy
      │
      ▼
  5. create_note(path, content)
     └── Path determined by vault organization pattern
      │
      ▼
  6. record_session_activity("note_created", summary, [path])
     └── Tracks for deduplication and session review
      │
      ▼
  7. create_daily_entry(summary, tags, links)
     └── Adds timestamped entry to daily note
```

---

## 10. Skill Specifications

### 10.1 /document-it

```yaml
---
name: document-it
description: Document the current context — a function, file, decision, or concept — as a structured Obsidian note. Use when the user wants to create documentation about something they're working on.
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

**Workflow**:
1. Read vault config for conventions (naming, tags, folder structure)
2. Analyze `$ARGUMENTS` and current conversation context to understand what to document
3. Search vault for related existing notes
4. Determine appropriate note location based on vault organization
5. Create note with proper frontmatter, tags, wikilinks
6. Record the activity and add a daily note entry

### 10.2 /capture-learning

```yaml
---
name: capture-learning
description: Capture what was learned during this session as a structured learning note. Use after solving a hard problem, discovering something new, or when the user wants to record knowledge.
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

**Workflow**:
1. Read vault config and session state
2. Analyze session transcript for learnings (focus on `$ARGUMENTS` if provided)
3. Create structured learning note with sections:
   - **Context**: What was being worked on
   - **What I Learned**: The key insight(s)
   - **Why It Matters**: Broader applicability
   - **Related**: Wikilinks to related vault notes
4. Place in appropriate folder (learning folder or detected convention)
5. Tag with relevant topic tags from vault taxonomy
6. Add daily note entry with wikilink to learning note
7. If the learning relates to an accomplishment, suggest brag doc update (respecting autonomy config)

### 10.3 /review-session

```yaml
---
name: review-session
description: Generate a session review — summarize what was done, decisions made, issues resolved. Use at the end of a work session to create a daily note entry and optionally update the brag doc.
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

**Workflow**:
1. Read session state to see what's already been logged
2. Analyze full session transcript for:
   - Activities performed (coding, debugging, researching, documenting)
   - Key decisions made
   - Issues encountered and resolved
   - Notes already created (from session state)
3. Generate high-level summary (2-3 lines with timestamps)
4. Append to daily note under configured heading
5. Include wikilinks to any notes created during the session
6. Check for brag-worthy accomplishments and update brag doc (respecting autonomy)

### 10.4 /brain-status

```yaml
---
name: brain-status
description: Show the current state of the Obsidian Brain integration — vault connection, today's activity, recent memories, and configuration.
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

**Workflow**:
1. Check vault connection and onboarding status
2. Read today's daily note for session log summary
3. Read current session state
4. List recent memories
5. Present formatted status report

### 10.5 /brain-config

```yaml
---
name: brain-config
description: Configure the Obsidian Brain plugin's autonomy levels and behavior preferences. Use to change how proactive the brain is during sessions.
argument-hint: "[setting] [value]"
user-invocable: true
allowed-tools:
  - mcp__obsidian-brain__get_brain_config
  - mcp__obsidian-brain__update_brain_config
---
```

**Workflow**:
1. If `$ARGUMENTS` provided: parse setting and value, update config
2. If no arguments: display current config and explain each setting
3. Present available autonomy levels and their meaning
4. Apply changes via `update_brain_config` MCP tool

---

## 11. Hook Specifications

### 11.1 session-start.py

**Input** (stdin JSON):
```json
{
  "session_id": "abc123",
  "cwd": "/home/user/project",
  "hook_event_name": "SessionStart"
}
```

**Logic**:
```python
1. Read session_id from stdin
2. Read Obsidian Brain config via REST API:
   - GET /vault/Obsidian Brain/config.yml
   - Extract autonomy settings
3. Check autonomy.session_start_context:
   - If "disabled": exit 0 (no output)
   - If "silent" or "prompt": continue
4. Read today's daily note:
   - GET /periodic/daily/{year}/{month}/{day}/
   - Extract section under configured heading
5. Initialize session state file:
   - /tmp/obsidian-brain-{session_id}.json
6. Output JSON:
   {
     "hookSpecificOutput": {
       "hookEventName": "SessionStart",
       "additionalContext": "🧠 Brain connected to vault.\n\nToday's sessions:\n- [09:30] Debugged auth issue...\n\nRecent memories: vault-overview, conventions\n\nAutonomy: learning capture=prompt, daily log=silent, brag doc=prompt"
     }
   }
```

**Performance target**: < 2 seconds (two HTTP calls to local API)

### 11.2 session-end-check.py (prompt type)

This is a `prompt`-type hook, so it's a string, not a script. The prompt instructs Haiku to evaluate the transcript:

```
Evaluate if this Claude Code session contained noteworthy content that should be captured in the user's Obsidian knowledge base.

Noteworthy content includes:
- Bugs fixed (especially non-trivial ones)
- New concepts or techniques learned
- Significant features implemented
- Important decisions made with reasoning
- Problems solved after extended investigation
- Useful patterns or approaches discovered

NOT noteworthy:
- Simple questions and answers
- Trivial edits or formatting changes
- Brief configuration or setup tasks
- Casual conversation

If noteworthy, respond with a brief (1-2 sentence) summary of what should be captured.
If not noteworthy, respond with exactly: "nothing noteworthy"
```

### 11.3 periodic-checkin.py

**Input** (stdin JSON):
```json
{
  "session_id": "abc123",
  "hook_event_name": "Stop"
}
```

**Logic**:
```python
1. Read session_id from stdin
2. Read session state from /tmp/obsidian-brain-{session_id}.json
3. Read config for checkin_interval_minutes
4. If autonomy.periodic_checkin == "disabled": exit 0
5. Calculate time since last_checkin
6. If elapsed < interval: exit 0 (no output)
7. Update last_checkin in state file
8. Output JSON:
   {
     "hookSpecificOutput": {
       "hookEventName": "Stop",
       "additionalContext": "🧠 It's been a while since we last checked in. Is there anything from this session worth noting down? You can:\n- /capture-learning to record what you've learned\n- /document-it to document something you're working on\n- Or just say 'nothing for now' to continue"
     }
   }
```

**Performance target**: < 500ms (file I/O only, no network)

---

## 12. Brag Doc Engine

### Location Detection

When `brag_doc_path` is `null` in config, the plugin auto-detects:

1. Search vault for existing brag-doc-like notes:
   - `search_content("brag doc")` or `search_content("accomplishments")`
   - Check for notes tagged `#brag-doc` or `#career`
2. If found: use that path
3. If not found: create based on vault organization:
   - PARA → `Areas/Career/Brag Doc.md`
   - Zettelkasten → `Permanent/Brag Doc.md`
   - Custom → `Obsidian Brain/Brag Doc.md` (fallback)

### Brag Doc Structure

```markdown
---
tags: [brag-doc, career]
updated: 2026-02-05
brain-managed: true
---

# Brag Doc

> Accomplishments automatically tracked by Obsidian Brain.
> Entries are added as you work — review and curate periodically.

## Features Built

- **2026-02-05**: Implemented real-time collaboration for document editing [[Collab Feature Design]]

## Bugs Fixed

- **2026-02-05**: Resolved authentication race condition affecting 12% of login attempts [[Auth Cache Fix]]

## Improvements

- **2026-02-04**: Reduced API response time by 40% through query optimization [[Performance Notes]]

## Key Learnings

- **2026-02-05**: Token refresh race conditions require mutex locks, not just retries [[Race Conditions]]
```

### Deduplication Strategy

The `append_to_brag_doc` MCP tool:
1. Reads current brag doc content
2. Checks if an entry with the same description already exists (fuzzy match on date + description)
3. If duplicate found: skip and return "already recorded"
4. If new: append under the correct category heading
5. Update the `updated` frontmatter field

---

## 13. Open Question Resolutions

| # | Question | Resolution | Rationale |
|---|----------|-----------|-----------|
| Q1 | Marketplace repo separate or same? | **Same repo** — `marketplace.json` at `.claude-plugin/` | Simplifies maintenance. Single repo is both plugin and marketplace. Users add this repo as a marketplace. |
| Q2 | Python dependency handling? | **`uvx --from git+...`** in `.mcp.json` | UV handles the virtualenv. Users need `uv` installed (standard Python tooling). No complex install scripts. |
| Q3 | Periodic check-in mechanism? | **`Stop` hook with `command` type** + temp file timestamps | Stop fires every time Claude finishes responding. The script checks elapsed time and exits silently (no-op) if the interval hasn't passed. Fast (~500ms) and non-intrusive. |
| Q4 | Multi-user vaults? | **Deferred** — single-user for v0.2 | Session logs include session_id but not user identity. Multi-user is a future consideration when team vaults are better understood. |
| Q5 | Brag doc categories configurable? | **Yes** — stored in `plugin.brag_doc_categories` config | Defaults to 4 standard categories. Users can customize via `/brain-config`. |
| Q6 | Vault conflict handling? | **Append-only operations** + heading-based targeting | All plugin writes are appends (never overwrite). Daily note entries go under a specific heading. Brag doc entries append to category headings. If a heading is missing, it's recreated. |

---

## 14. Migration Strategy

### From Standalone MCP to Plugin

The migration is **additive** — existing MCP functionality is preserved:

**Phase 1: Plugin Scaffold**
- Add `.claude-plugin/plugin.json`
- Add `.claude-plugin/marketplace.json`
- Modify `.mcp.json` to use `${CLAUDE_PLUGIN_ROOT}` (with fallback)
- No changes to existing Python code

**Phase 2: Session Tools**
- Add `tools/session.py` with 5 new MCP tools
- Register in `server.py`
- No changes to existing tools

**Phase 3: Skills**
- Add 5 SKILL.md files in `skills/`
- Pure additions, no existing code changes

**Phase 4: Hooks**
- Add `hooks/hooks.json`
- Add 3 hook scripts in `scripts/`
- Add `scripts/brain-state.py` shared module
- Pure additions, no existing code changes

**Phase 5: Config Extension**
- Extend onboarding to include `autonomy` and `plugin` config sections
- Backward-compatible — missing sections use defaults

### Backward Compatibility

Users who use obsidian-brain as a standalone MCP server (without the plugin) continue to work exactly as before. The new tools (`session.py`) are optional — they only matter when called by skills or hooks. The config extensions are backward-compatible with defaults.

---

## Appendix: Requirement Traceability

| Requirement | Addressed By |
|------------|-------------|
| D-1 (single install) | Plugin manifest + marketplace |
| D-2 (manifest) | `.claude-plugin/plugin.json` |
| D-3 (MCP bundled) | `.mcp.json` with `${CLAUDE_PLUGIN_ROOT}` |
| D-5 (portable paths) | All configs use `${CLAUDE_PLUGIN_ROOT}` |
| D-6 (env vars) | Obsidian API env vars in `.mcp.json` |
| D-7 (onboarding) | Existing onboarding + session-start.py check |
| SK-1 through SK-30 | Skill SKILL.md specifications |
| H-1 through H-19 | Hook specifications |
| DN-1 through DN-8 | Daily note flow + `create_daily_entry` tool |
| BD-1 through BD-8 | Brag doc engine |
| CA-1 through CA-8 | Configuration system |
| VC-1 through VC-7 | Vault config integration in all skills |
| NT-1 through NT-5 | Session state management |
| NF-1 through NF-8 | Performance targets in hook specs |
