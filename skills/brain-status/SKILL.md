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

## Purpose

Display a comprehensive status report of the Obsidian Brain integration. Shows vault connection health, today's activity, session state, available memories, and current configuration.

## Workflow

1. **Check vault connection**: Call `check_onboarding_status` to verify the vault is reachable and configured.

2. **Load configuration**: Call `get_brain_config` to get autonomy settings and plugin preferences.

3. **Get today's daily note**: Call `get_daily_note` to see today's session log entries.

4. **Get session state**: Call `get_session_state` to see what's happened this session.

5. **List memories**: Call `list_memories` to show available cross-session context.

6. **Check knowledge base**: Call `get_knowledge_base_status` to see if a knowledge base exists.

7. **Present the status report** in the format below.

## Output Format

Present a clean status report:

```
## Brain Status

**Vault**: Connected (onboarded)
**Version**: 0.2.0

### Today's Activity
- 2 sessions logged
- 3 notes created
- Last entry: [HH:MM] Summary...

### This Session
- Started: HH:MM
- Notes created: 1
- Daily entries: 2

### Memories (5 available)
- vault-overview (vault-overview)
- conventions (conventions)
- project-context (project)
- ...

### Knowledge Base
- Status: Generated (last: YYYY-MM-DD)

### Autonomy Settings
- Session start context: silent
- Learning capture: prompt
- Daily log: silent
- Brag doc: prompt
- Periodic check-in: prompt (every 30 min)
```

## Conventions

- If vault is not reachable, show "Vault: Offline" and suggest checking Obsidian
- If not onboarded, suggest running onboarding
- Keep the report concise and scannable
- Show the most actionable information first
