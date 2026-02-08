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

## Purpose

Create a structured Obsidian note documenting the specified topic from the current coding context. The note follows vault conventions and integrates with the existing knowledge graph through tags and wikilinks.

## Prerequisites

1. Call `get_brain_config` to load autonomy preferences and plugin settings
2. Call `get_vault_config` to load vault conventions (naming patterns, tag taxonomy, folder structure)

## Workflow

1. **Understand the topic**: Analyze `$ARGUMENTS` and the current conversation context to determine what to document. If `$ARGUMENTS` is empty, ask the user what they'd like to document.

2. **Search for related notes**: Call `search_content` with relevant keywords to find existing notes that should be linked. Also call `list_all_tags` to see the vault's tag taxonomy.

3. **Determine note location**: Based on vault organization patterns from `get_vault_config`:
   - **PARA**: Place in appropriate category (Projects/Areas/Resources)
   - **Zettelkasten**: Place in appropriate note type folder
   - **Custom**: Follow the detected folder conventions
   - Use the naming pattern detected during onboarding (Title Case, date-prefixed, etc.)

4. **Compose note content**: Create the note with:
   - YAML frontmatter with convention-appropriate keys
   - Clear heading structure
   - Wikilinks to related notes found in step 2
   - Tags from the vault taxonomy

5. **Create the note**: Call `create_note` with the composed path and content.

6. **Track and log**: Call `record_session_activity` with type `note_created` and the note path. Then call `create_daily_entry` with a brief summary and a wikilink to the new note.

## Output Format

```markdown
---
tags: [relevant, tags, from-taxonomy]
created: YYYY-MM-DD
type: documentation
---

# [Topic Title]

## Overview
Brief description of what this documents.

## Details
Main content — code explanations, decision rationale, concept description.

## Related
- [[Related Note 1]] — how it connects
- [[Related Note 2]] — how it connects
```

## Conventions

- Always use the vault's naming pattern for the note title
- Place tags in frontmatter (not inline) unless the vault primarily uses inline tags
- Include `created` date in frontmatter
- Link to related existing notes using `[[wikilinks]]`
- Adapt the heading structure to match the document type:
  - **Function/code doc**: Overview, Parameters, Return Value, Example, Related
  - **Decision record**: Context, Decision, Consequences, Related
  - **Concept note**: Overview, Key Points, Examples, Related
