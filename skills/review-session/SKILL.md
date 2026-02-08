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

## Purpose

Generate a comprehensive session review that summarizes work done, decisions made, and issues resolved. The review is logged in the daily note and significant accomplishments are tracked in the brag doc.

## Prerequisites

1. Call `get_brain_config` to load autonomy preferences
2. Call `get_session_state` to see what's already been logged this session (prevent duplicates)
3. Call `get_vault_config` to load vault conventions

## Workflow

1. **Check existing state**: Review `get_session_state` output for:
   - Notes already created (include wikilinks in summary)
   - Daily entries already made (avoid duplication)
   - Brag entries already recorded

2. **Analyze the session transcript**: Summarize:
   - **Activities**: What was done (coding, debugging, researching, documenting)
   - **Decisions**: Key choices made with rationale
   - **Issues**: Problems encountered and how they were resolved
   - **Outcomes**: What was achieved

3. **Generate daily note summary**: Create a concise 2-3 line summary with timestamps:
   ```
   - [HH:MM-HH:MM] Summary of session activities
   - Created: [[Note 1]], [[Note 2]]
   - Key decision: [brief description]
   ```

4. **Append to daily note**: Call `append_to_daily` with the summary, using the configured heading from `plugin.daily_note_heading`.

5. **Check for brag-worthy accomplishments**: If the session included notable achievements, check `autonomy.brag_doc_update`:
   - If `"silent"`: call `append_to_brag_doc` for each accomplishment
   - If `"prompt"`: present accomplishments to user and ask if they should be added
   - If `"disabled"`: skip

6. **Track**: Call `record_session_activity` with type `session_reviewed`.

## Output Format

Present the review to the user in a clean format:

```
## Session Review

**Duration**: ~X minutes
**Activities**: coding, debugging
**Notes created**: [[Note 1]], [[Note 2]]

### Summary
Brief overview of what happened.

### Key Decisions
- Decision 1: rationale

### Brag-worthy
- [Category]: Description
```

## Conventions

- Include wikilinks to all notes created during the session
- Use timestamps from session state for accuracy
- Keep daily note entries concise (2-3 lines max)
- Only suggest brag doc entries for genuinely notable work
