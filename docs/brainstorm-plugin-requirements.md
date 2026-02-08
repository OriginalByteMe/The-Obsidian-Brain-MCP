# Obsidian Brain — Claude Code Plugin Requirements

> **Status**: Requirements Discovery (Brainstorm Output)
> **Date**: 2026-02-05
> **Next Step**: `/sc:design` for architecture, `/sc:workflow` for implementation planning

---

## Vision Statement

Transform Obsidian Brain MCP from a standalone MCP server into a **distributable Claude Code plugin** that acts as a persistent knowledge management companion. The plugin bundles the MCP server alongside skills, hooks, and automated behaviors that proactively maintain the user's Obsidian vault as a byproduct of normal coding sessions.

**Core Philosophy**: The LLM shouldn't just *respond* to vault requests — it should **proactively maintain** the user's knowledge system, capturing learnings, logging sessions, and building a living record of the developer's work.

---

## 1. Distribution & Installation

### Requirements

| ID | Requirement | Priority |
|----|------------|----------|
| D-1 | Plugin installable via single command (`/plugin install obsidian-brain@marketplace`) | Must |
| D-2 | Plugin manifest (`.claude-plugin/plugin.json`) with full metadata | Must |
| D-3 | MCP server bundled via `.mcp.json` at plugin root | Must |
| D-4 | Marketplace repository for public distribution | Must |
| D-5 | `${CLAUDE_PLUGIN_ROOT}` used for all internal paths (portable installation) | Must |
| D-6 | Environment variable configuration for Obsidian API connection | Must |
| D-7 | First-run onboarding flow that detects vault conventions | Should |

### Plugin Directory Structure

```
obsidian-brain/
  .claude-plugin/
    plugin.json                    # Plugin manifest
  .mcp.json                        # MCP server configuration
  skills/
    document-it/
      SKILL.md                     # /document-it skill
    capture-learning/
      SKILL.md                     # /capture-learning skill
    review-session/
      SKILL.md                     # /review-session skill
    brain-status/
      SKILL.md                     # /brain-status skill
    brain-config/
      SKILL.md                     # /brain-config skill
  hooks/
    hooks.json                     # Hook configurations
  scripts/
    session-start.sh               # Session start hook script
    session-end-check.sh           # Session end hook script
    periodic-checkin.sh            # Periodic check-in script
  src/
    obsidian_brain/                # Existing MCP server code
      ...
  pyproject.toml
  README.md
  LICENSE
```

---

## 2. Skills (Slash Commands)

### 2.1 `/document-it`

**Purpose**: Document the current context — a function, file, decision, or concept — as a structured Obsidian note.

| ID | Requirement | Priority |
|----|------------|----------|
| SK-1 | Accept argument specifying what to document (file, function, concept, decision) | Must |
| SK-2 | Auto-detect appropriate note template based on content type | Should |
| SK-3 | Generate frontmatter with relevant tags based on vault conventions | Must |
| SK-4 | Create wikilinks to related existing notes (detected via search) | Should |
| SK-5 | Place note in correct vault location based on detected organization pattern | Must |
| SK-6 | Add backlink from daily note to created documentation | Should |
| SK-7 | Respect vault naming conventions (detected during onboarding) | Must |

**User Story**: *As a developer, I want to type `/document-it authentication flow` and have a well-structured note created in my vault that documents what I'm currently working on, properly tagged and linked.*

### 2.2 `/capture-learning`

**Purpose**: Capture what was learned during the current session as a structured learning note.

| ID | Requirement | Priority |
|----|------------|----------|
| SK-8 | Analyze session transcript to identify key learnings | Must |
| SK-9 | Create structured learning note with: context, what was learned, why it matters | Must |
| SK-10 | Tag with relevant topic tags from vault taxonomy | Must |
| SK-11 | Link to related existing knowledge in vault | Should |
| SK-12 | Add entry to daily note referencing the learning | Must |
| SK-13 | Optionally update brag doc if the learning relates to an achievement | Should |
| SK-14 | Support user-provided focus ("capture-learning about the caching bug") | Should |

**User Story**: *As a developer, after debugging a complex caching issue for an hour, I want to type `/capture-learning` and have a note created that captures the root cause, the fix, and the general lesson — linked to my daily note and relevant project notes.*

### 2.3 `/review-session`

**Purpose**: Generate a comprehensive session review — summarize what was done, decisions made, issues encountered.

| ID | Requirement | Priority |
|----|------------|----------|
| SK-15 | Analyze full session transcript for activities, decisions, and outcomes | Must |
| SK-16 | Generate high-level summary (2-3 lines) with timestamps | Must |
| SK-17 | Include wikilink references to any notes created during the session | Must |
| SK-18 | Append review to today's daily note under a configurable heading | Must |
| SK-19 | Categorize activities (coding, debugging, researching, documenting) | Should |
| SK-20 | Identify unresolved issues and create follow-up items | Should |
| SK-21 | Update brag doc with notable accomplishments from the session | Should |

**User Story**: *As a developer ending my coding session, I want to type `/review-session` and have a structured summary appended to my daily note, with links to everything I created or worked on.*

### 2.4 `/brain-status`

**Purpose**: Show the current state of the Obsidian Brain integration — what's tracked, recent activity, health.

| ID | Requirement | Priority |
|----|------------|----------|
| SK-22 | Show vault connection status and statistics | Must |
| SK-23 | Display today's daily note summary (what's been logged so far) | Must |
| SK-24 | Show recent memories and their relevance | Should |
| SK-25 | Report on brag doc status (last updated, entry count) | Should |
| SK-26 | Display current autonomy settings | Should |

### 2.5 `/brain-config`

**Purpose**: Configure the plugin's autonomy levels and behavior preferences.

| ID | Requirement | Priority |
|----|------------|----------|
| SK-27 | Allow toggling autonomy per behavior (session logging, brag doc, learning capture) | Must |
| SK-28 | Set preferred detail level for daily note entries | Should |
| SK-29 | Configure check-in frequency for long sessions | Should |
| SK-30 | Store preferences in `.obsidian-brain/config.yml` in the vault | Must |

---

## 3. Hooks (Lifecycle Automation)

### 3.1 Session Start Hook

**Event**: `SessionStart`

| ID | Requirement | Priority |
|----|------------|----------|
| H-1 | Read today's daily note and inject summary as context | Must |
| H-2 | Load recent relevant memories from `.obsidian-brain/memories/` | Must |
| H-3 | Display brief context message: "Brain connected. Today so far: [summary]" | Must |
| H-4 | Check if vault is onboarded; prompt onboarding if not | Should |
| H-5 | Load user's autonomy preferences from vault config | Must |

**Behavior**: Non-blocking. Provides context to Claude without interrupting the user. The summary should be concise — 2-3 lines max showing what's been logged to the daily note today.

### 3.2 Session End Hook

**Event**: `Stop` (when Claude finishes responding and session may end)

| ID | Requirement | Priority |
|----|------------|----------|
| H-6 | Evaluate if the session contained noteworthy content (learnings, decisions, issues resolved) | Must |
| H-7 | If noteworthy: prompt user "Would you like to capture what you learned?" with options | Must |
| H-8 | Options: "Capture learnings", "Just log to daily note", "Skip" | Must |
| H-9 | If "Capture learnings": invoke `/capture-learning` flow | Must |
| H-10 | If "Just log": append brief session summary to daily note | Must |
| H-11 | Always update daily note with session activity log (unless user has disabled) | Should |
| H-12 | Update brag doc if accomplishments detected (configurable) | Should |
| H-13 | Respect user's autonomy settings — some users want this silent, others want prompts | Must |

**Behavior**: Uses a `prompt`-type hook to evaluate session content, then conditionally triggers actions. Respects the user's configured autonomy level.

### 3.3 Periodic Check-in

**Event**: `Stop` (with time-based logic — check if sufficient time has elapsed)

| ID | Requirement | Priority |
|----|------------|----------|
| H-14 | Track elapsed session time (via timestamps in hook script) | Must |
| H-15 | After configurable interval (~30 min of activity), suggest noting things down | Must |
| H-16 | Gentle, non-intrusive prompt: "It's been a while — anything worth noting?" | Must |
| H-17 | Accept "not now" gracefully and reset timer | Must |
| H-18 | Configurable: can be disabled entirely, or interval adjusted | Must |
| H-19 | Smart detection: only trigger if substantive work happened (not idle) | Should |

**Behavior**: Implemented as a `Stop` hook with a script that tracks time since last check-in. Only fires if enough time has passed AND the session is still active.

---

## 4. Daily Note Integration

### Requirements

| ID | Requirement | Priority |
|----|------------|----------|
| DN-1 | Maintain a running log of Claude Code sessions in today's daily note | Must |
| DN-2 | Each session entry includes: timestamp, high-level summary, wikilinks to created notes | Must |
| DN-3 | Entries appended under a configurable heading (default: "## Claude Code Sessions") | Must |
| DN-4 | Format: `- [HH:MM] Summary of what was done [[Created Note 1]] [[Created Note 2]]` | Must |
| DN-5 | Track what has already been written to avoid duplication | Must |
| DN-6 | Support multiple sessions per day (append, don't overwrite) | Must |
| DN-7 | If daily note doesn't exist, create it using detected template conventions | Should |
| DN-8 | Graceful handling when Obsidian daily notes plugin isn't configured | Must |

### Daily Note Entry Format

```markdown
## Claude Code Sessions

- [09:30] Debugged authentication caching issue — found race condition in token refresh. [[Authentication Cache Fix]] [[Learning - Race Conditions in Token Refresh]]
- [14:15] Implemented new API endpoint for user preferences. [[API Preferences Endpoint]]
- [16:45] Code review and refactoring of payment module. No new notes created.
```

---

## 5. Brag Document

### Requirements

| ID | Requirement | Priority |
|----|------------|----------|
| BD-1 | Maintain a single evolving "Brag Doc" note in the vault | Must |
| BD-2 | Location configurable; default to detected organization pattern | Must |
| BD-3 | Structured with categories: Features Built, Bugs Fixed, Improvements, Learnings | Should |
| BD-4 | Each entry includes: date, brief description, optional wikilinks to related notes | Must |
| BD-5 | Updated automatically when sessions produce notable accomplishments | Should |
| BD-6 | Manual update via `/review-session` when accomplishments detected | Must |
| BD-7 | Avoid duplicate entries (track what's been added) | Must |
| BD-8 | Configurable: user can disable automatic updates, keep manual-only | Must |

### Brag Doc Format

```markdown
---
tags: [brag-doc, career]
updated: 2026-02-05
---

# Brag Doc

## Features Built
- **2026-02-05**: Implemented real-time collaboration for document editing [[Collab Feature Design]]
- **2026-02-03**: Built API rate limiting middleware with sliding window algorithm

## Bugs Fixed
- **2026-02-05**: Resolved authentication race condition affecting 12% of login attempts [[Authentication Cache Fix]]

## Improvements
- **2026-02-04**: Reduced API response time by 40% through query optimization [[Performance Optimization Notes]]

## Key Learnings
- **2026-02-05**: Discovered that token refresh race conditions require mutex locks, not just retries [[Learning - Race Conditions in Token Refresh]]
```

---

## 6. Configurable Autonomy System

### Requirements

| ID | Requirement | Priority |
|----|------------|----------|
| CA-1 | All proactive behaviors have three autonomy levels: `silent`, `prompt`, `disabled` | Must |
| CA-2 | `silent`: behavior runs automatically, result shown in status | Must |
| CA-3 | `prompt`: behavior asks user before executing | Must |
| CA-4 | `disabled`: behavior never runs | Must |
| CA-5 | Preferences stored in `.obsidian-brain/config.yml` in the vault | Must |
| CA-6 | Sensible defaults that lean toward `prompt` (ask first) | Must |
| CA-7 | Configurable via `/brain-config` skill | Must |
| CA-8 | Configuration changes take effect immediately (no restart needed) | Should |

### Default Autonomy Configuration

```yaml
# .obsidian-brain/config.yml (additions to existing config)
autonomy:
  session_start_context: silent        # Always load context silently
  session_end_learning_capture: prompt  # Ask before capturing learnings
  session_end_daily_log: silent         # Always log to daily note
  brag_doc_update: prompt               # Ask before updating brag doc
  periodic_checkin: prompt              # Ask during long sessions
  checkin_interval_minutes: 30          # How often to check in
  daily_note_heading: "## Claude Code Sessions"
  brag_doc_path: null                   # Auto-detect or set manually
```

---

## 7. Vault Convention Awareness

### Requirements

| ID | Requirement | Priority |
|----|------------|----------|
| VC-1 | Leverage existing onboarding system to detect vault patterns (PARA, Zettelkasten, flat, custom) | Must |
| VC-2 | All note creation respects detected naming conventions | Must |
| VC-3 | Tag suggestions drawn from existing vault taxonomy | Must |
| VC-4 | Note placement follows detected folder organization | Must |
| VC-5 | Template usage matches detected patterns (if templates exist) | Should |
| VC-6 | Frontmatter structure matches existing conventions | Must |
| VC-7 | If conventions change (user reorganizes), re-onboarding updates behavior | Should |

---

## 8. Note Tracking & Deduplication

### Requirements

| ID | Requirement | Priority |
|----|------------|----------|
| NT-1 | Track all notes created/modified by the plugin in current session | Must |
| NT-2 | Track all daily note entries made in current session | Must |
| NT-3 | Prevent duplicate entries when multiple hooks or skills fire | Must |
| NT-4 | Session state persisted in memory for hook scripts to access | Must |
| NT-5 | Cross-session tracking via `.obsidian-brain/memories/` | Should |

---

## 9. Non-Functional Requirements

| ID | Requirement | Priority |
|----|------------|----------|
| NF-1 | Hook scripts execute within 5 seconds (no blocking the user) | Must |
| NF-2 | MCP server startup within 3 seconds | Must |
| NF-3 | Graceful degradation when Obsidian is not running (clear error, no crash) | Must |
| NF-4 | Works with Obsidian Local REST API plugin (existing dependency) | Must |
| NF-5 | Python 3.12+ (existing requirement) | Must |
| NF-6 | No additional system dependencies beyond existing (httpx, pydantic, etc.) | Should |
| NF-7 | Plugin self-validates on install (checks Obsidian API connectivity) | Should |
| NF-8 | All vault writes are idempotent where possible | Should |

---

## 10. User Stories Summary

1. **As a developer**, I install obsidian-brain with one command and it auto-detects my vault structure, so I can start capturing knowledge immediately.

2. **As a developer**, when I start a Claude Code session, I see a brief summary of what I worked on today, so I have continuity across sessions.

3. **As a developer**, I type `/document-it` to instantly create a well-structured note about what I'm working on, properly tagged and linked within my vault.

4. **As a developer**, I type `/capture-learning` after solving a hard problem, and a learning note is created with context, linked to my daily note and related concepts.

5. **As a developer**, at the end of a session, I'm gently asked if I want to capture what I learned, so nothing falls through the cracks.

6. **As a developer**, my daily note automatically accumulates a log of my Claude Code sessions with timestamps and links, giving me a record of my day.

7. **As a developer**, my brag doc stays up to date with my accomplishments without me having to remember to update it.

8. **As a developer**, during a long debugging session, the brain gently reminds me to note things down, catching insights I might forget.

9. **As a developer**, I control exactly how autonomous each behavior is — some I want silent, some I want to approve, some I want off.

10. **As a developer**, regardless of whether my vault uses PARA, Zettelkasten, or a custom system, the brain adapts to my conventions.

---

## 11. Open Questions

| # | Question | Impact |
|---|----------|--------|
| Q1 | Should the marketplace be a separate repo or part of this repo? | Distribution architecture |
| Q2 | How to handle the MCP server's Python dependency in a plugin context? Users need Python + UV. Should the plugin auto-install? | Installation UX |
| Q3 | Should the periodic check-in use `Stop` hook with time tracking, or is there a better mechanism? | Hook implementation |
| Q4 | What happens when multiple users share a vault (e.g., team vaults)? Should session logs be per-user? | Multi-user support |
| Q5 | Should the brag doc categories be configurable or fixed? | Brag doc flexibility |
| Q6 | How should the plugin handle vault conflicts (e.g., user manually edited a section the brain wants to append to)? | Data integrity |

---

## 12. Existing Assets to Leverage

The current codebase already provides significant infrastructure:

| Asset | Location | Reuse Strategy |
|-------|----------|---------------|
| MCP Server (32 tools) | `src/obsidian_brain/` | Bundle as-is in plugin `.mcp.json` |
| Daily note tools | `tools/daily.py` | Foundation for DN-1 through DN-8 |
| Memory system | `memory.py` + `tools/memory.py` | Foundation for note tracking (NT-1 through NT-5) |
| Onboarding & convention detection | `onboarding.py` | Foundation for VC-1 through VC-7 |
| Knowledge base | `knowledge.py` | Reuse for vault context in session start |
| Vault cache | `cache.py` | Reuse for efficient vault queries |
| Frontmatter utils | `utils/frontmatter.py` | Reuse for all note creation |
| Wikilinks utils | `utils/wikilinks.py` | Reuse for link generation |
| Tag tools | `tools/tags.py` | Reuse for convention-aware tagging |

---

## Next Steps

1. **`/sc:design`** — Architecture the plugin structure, hook implementation, and skill definitions
2. **`/sc:workflow`** — Create phased implementation plan
3. **Implementation** — Build incrementally, starting with plugin scaffold → skills → hooks → automation
