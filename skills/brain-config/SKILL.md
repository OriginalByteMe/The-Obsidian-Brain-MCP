---
name: brain-config
description: Configure the Obsidian Brain plugin's autonomy levels and behavior preferences. Use to change how proactive the brain is during sessions.
argument-hint: "[setting] [value]"
user-invocable: true
allowed-tools:
  - mcp__obsidian-brain__get_brain_config
  - mcp__obsidian-brain__update_brain_config
---

## Purpose

View and modify the Obsidian Brain plugin's configuration. Controls how proactive the plugin is during sessions — from fully autonomous to completely manual.

## Workflow

### If no arguments provided:

1. Call `get_brain_config` to load current settings
2. Display all settings with their current values and explanations (see format below)
3. Wait for the user to specify what to change

### If arguments provided:

1. Parse `$ARGUMENTS` for a setting name and value
2. Validate the value is appropriate for the setting
3. Call `update_brain_config` with the dot-notation key and new value
4. Confirm the change

## Available Settings

### Autonomy Settings (autonomy.*)

Each autonomy setting accepts one of three values:
- **`silent`**: Acts automatically without asking
- **`prompt`**: Asks the user before acting
- **`disabled`**: Never acts

| Setting | Key | Default | Description |
|---------|-----|---------|-------------|
| Session start context | `autonomy.session_start_context` | `silent` | Show vault context when session starts |
| Learning capture | `autonomy.session_end_learning_capture` | `prompt` | Capture learnings at session end |
| Daily log | `autonomy.session_end_daily_log` | `silent` | Log session to daily note |
| Brag doc | `autonomy.brag_doc_update` | `prompt` | Update brag doc with accomplishments |
| Periodic check-in | `autonomy.periodic_checkin` | `prompt` | Remind to capture notes periodically |

### Plugin Settings (plugin.*)

| Setting | Key | Default | Description |
|---------|-----|---------|-------------|
| Check-in interval | `plugin.checkin_interval_minutes` | `30` | Minutes between periodic check-ins |
| Daily note heading | `plugin.daily_note_heading` | `## Claude Code Sessions` | Heading for session entries |
| Brag doc path | `plugin.brag_doc_path` | `null` (auto-detect) | Explicit path to brag doc |
| Session log format | `plugin.session_log_format` | `summary` | Format: `summary` or `structured` |

## Output Format

When displaying config:

```
## Brain Configuration

### Autonomy Levels
- Session start context: **silent** — shows vault context automatically
- Learning capture: **prompt** — asks before capturing learnings
- Daily log: **silent** — logs sessions automatically
- Brag doc: **prompt** — asks before updating brag doc
- Periodic check-in: **prompt** — reminds every 30 min

### Plugin Settings
- Check-in interval: 30 minutes
- Daily note heading: ## Claude Code Sessions
- Brag doc path: auto-detect
- Session log format: summary

To change a setting:
  /brain-config autonomy.brag_doc_update silent
  /brain-config plugin.checkin_interval_minutes 45
```

## Conventions

- When updating, confirm the change was applied
- Warn if setting an autonomy level to `silent` for destructive operations
- Suggest `disabled` rather than uninstalling if user wants to turn everything off
