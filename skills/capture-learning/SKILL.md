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

## Purpose

Analyze the current session's conversation to extract key learnings and create a structured learning note in the vault. This captures knowledge that might otherwise be lost after the session ends.

## Prerequisites

1. Call `get_brain_config` to load autonomy preferences
2. Call `get_vault_config` to load vault conventions
3. Call `get_session_state` to check what's already been captured this session

## Workflow

1. **Analyze the session**: Review the conversation transcript for learnings. If `$ARGUMENTS` is provided, focus the analysis on that topic. Look for:
   - Problems solved and how they were solved
   - New concepts or techniques discovered
   - Non-obvious insights or "aha moments"
   - Useful patterns or approaches

2. **Search for related notes**: Call `search_content` with the learning topic to find existing notes that provide context or should be linked.

3. **Determine note location**: Use vault conventions to place the learning note:
   - Check if a dedicated learning folder exists (from `get_vault_config`)
   - Check `plugin.learning_note_folder` from config
   - Fall back to vault organization conventions

4. **Create the learning note** with the structure below. Call `create_note`.

5. **Update daily note**: Call `create_daily_entry` with a summary like "Captured learning: [topic]" and a wikilink to the new note.

6. **Consider brag doc**: If the learning relates to an accomplishment (bug fixed, feature built), check `autonomy.brag_doc_update`:
   - If `"silent"`: call `append_to_brag_doc` directly
   - If `"prompt"`: suggest the brag doc update to the user
   - If `"disabled"`: skip

7. **Track**: Call `record_session_activity` with type `learning_captured`.

## Output Format

```markdown
---
tags: [learning, topic-specific-tags]
created: YYYY-MM-DD
type: learning
---

# [Learning Title]

## Context
What was being worked on when this was learned. Include project/task context.

## What I Learned
The key insight(s) — be specific and actionable. Include code examples if relevant.

## Why It Matters
Broader applicability — when would this knowledge be useful again?

## Related
- [[Related Note]] — connection to existing knowledge
```

## Conventions

- Title should be specific and searchable (e.g., "Race Conditions in Token Refresh" not "Concurrency Bug")
- Include code snippets in the "What I Learned" section when relevant
- Tag with topic-specific tags from the vault taxonomy
- Always link back to related existing notes
