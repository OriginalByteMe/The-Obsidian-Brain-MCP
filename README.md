<p align="center">
  <img src="assets/Obsidian_Flow State.png" alt="Obsidian Brain MCP" width="120" />
</p>

<h1 align="center">Obsidian Brain MCP</h1>

<p align="center">
  <strong>Bridge the gap between your AI conversations and your second brain</strong>
</p>

<p align="center">
  <a href="#installation"><img src="https://img.shields.io/badge/Install-uvx-blue?style=for-the-badge" alt="Install with uvx" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="MIT License" /></a>
  <a href="https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP"><img src="https://img.shields.io/badge/Python-3.12+-yellow?style=for-the-badge" alt="Python 3.12+" /></a>
</p>

<p align="center">
  <em>Stop losing insights to the void of AI chat history.<br/>Start building a knowledge graph that grows with every conversation.</em>
</p>

---

## The Problem

You've been there. Hours deep in a coding session or research rabbit hole with your AI assistant. Discoveries made. Problems solved. Concepts finally clicked.

Then you close the chat.

**Gone.**

All those insights, explanations, and breakthroughs scattered across a poorly saved claude code sessions or chatgpt chats history. Meanwhile, your Obsidian vault sits waiting, ready to connect ideas, but completely disconnected from where your best thinking actually happens.

## The Solution

**Obsidian Brain MCP** creates a living bridge between your AI assistant and your Obsidian vault. Your LLM doesn't just *respond*--it *remembers*, *organizes*, and *connects*.

```
AI Conversation  <->  Obsidian Brain MCP  <->  Your Vault
```

Now your assistant can:
- **Capture insights** directly into your vault as you discover them
- **Build connections** by linking new notes to existing knowledge
- **Search your mind** to find relevant notes you forgot you had
- **Understand your graph** and help you see patterns in your thinking
- **Match your style** by learning from how you actually write

---

## See It In Action

<p align="center">
  <img src="assets/ObsidianMCPDemo.gif" alt="Obsidian Brain MCP Demo" width="800" />
</p>

<p align="center">
  <em>Creating notes, building connections, and searching your vault--all through natural conversation.</em>
</p>

---

## Use Cases

<details>
<summary><strong>Learning & Research</strong></summary>

> *"Explain how React Server Components work"*

As your AI explains the concept, ask it to save key insights directly to your vault. It creates a note, links it to your existing `[[React]]` and `[[Frontend Architecture]]` notes, and tags it `#learning #react #server-components`.

Next week when you're debugging an RSC issue, your AI can search your vault and remind you of the mental model you built together.
</details>

<details>
<summary><strong>Coding Sessions</strong></summary>

> *"Help me debug this authentication flow"*

After 2 hours of debugging, you finally crack it. Instead of losing that hard-won knowledge, ask your AI to document the solution. It creates a note under `Development/Debugging` with:
- The symptoms you encountered
- The root cause
- The fix
- Links to related notes like `[[Auth Middleware]]` and `[[JWT Tokens]]`

Future you will thank present you.
</details>

<details>
<summary><strong>Writing & Content Creation</strong></summary>

> *"Let's brainstorm ideas for my blog post on AI productivity"*

As ideas flow, your AI captures them in a scratch note. When you land on a good angle, it writes a polished draft to your `Writing/Drafts` folder, adds relevant tags, and links to your research notes on `[[AI Tools]]` and `[[Personal Productivity]]`.

Your vault becomes your writing partner's memory.
</details>

<details>
<summary><strong>Meeting Notes & Action Items</strong></summary>

> *"Add today's standup notes to my daily note"*

Your AI appends a timestamped entry to today's daily note with discussion points, decisions made, and action items--all properly tagged and linked to relevant project notes.

```markdown
## 10:30 - Standup
- Discussed [[Project Alpha]] timeline
- Decision: Push launch to Q2 #decision
- Action: Review PR #142 by EOD #todo
```
</details>

<details>
<summary><strong>Personal Knowledge Management</strong></summary>

> *"What do I know about distributed systems?"*

Your AI searches your vault, finds 23 related notes across `Learning/`, `Projects/`, and `Books/`, and synthesizes a summary of your knowledge landscape. It identifies gaps and suggests areas to explore further.

Your scattered notes become a queryable knowledge base.
</details>

<details>
<summary><strong>Book & Article Notes</strong></summary>

> *"I just finished reading 'Thinking in Systems' - help me capture the key ideas"*

As you discuss the book, your AI creates structured literature notes in your preferred format, extracts key concepts into atomic notes, and weaves them into your existing knowledge graph with relevant backlinks.

Every book you read strengthens your second brain.
</details>

---

## Features

| Feature | Description |
|---------|-------------|
| **Full Vault Access** | Read, create, update, and organize notes without leaving your conversation |
| **Linking** | Resolve links the way Obsidian does, add `[[wikilinks]]`, and traverse backlinks and outgoing links up to three hops |
| **Tag Intelligence** | Add, remove, and search by tags across your entire vault |
| **Text Search** | Full-text search across your entire vault |
| **Daily Notes** | Seamless integration with daily notes |
| **Vault Onboarding** | AI learns your vault's structure, conventions, and patterns |
| **Persistent Memory** | Cross-session context that remembers previous interactions |
| **Knowledge Base** | Generate comprehensive vault overviews for deep AI understanding |

---

<a id="installation"></a>

## Prerequisites

1. **Obsidian 1.12.4+** (verified against 1.15) with the officially registered CLI:
   - In Obsidian, open **Settings > General > Advanced** and turn **Command line interface** on.
   - Accept the follow-up prompt to register it in your PATH. On Linux this copies Obsidian's bundled `obsidian-cli` to `~/.local/bin/obsidian` (mode 755); ensure `~/.local/bin` is on your PATH. On Windows it appends the install directory to the user PATH; on macOS it links into `/usr/local/bin`.
   - Verify the registration with `obsidian version` (for example, `1.15.1 (installer 1.15.0)`).
   - **Keep the Obsidian desktop app running** with the target vault loaded: the server works by running JavaScript inside Obsidian through the CLI's `eval` command, so there is no separate plugin to install and nothing is read from disk behind Obsidian's back.
   - `OBSIDIAN_CLI_PATH` remains available when you need to point at the binary explicitly.
   - **Daily notes core plugin** enabled (Settings > Core plugins), if you use `get_daily_note` or `append_to_daily`; they use its folder, date format and template.
2. **uv** package manager: [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

## Installation

Add to your MCP client configuration:

<details>
<summary><strong>Cursor</strong></summary>

Add to `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project):

```json
{
  "mcpServers": {
    "obsidian-brain": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"]
    }
  }
}
```

See [Cursor MCP docs](https://docs.cursor.com/context/model-context-protocol) for more details.
</details>

<details>
<summary><strong>Claude Desktop / Claude Code</strong></summary>

**Config location:**
- Linux: `~/.config/claude-desktop/claude_desktop_config.json` or `~/.claude.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "obsidian-brain": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP",
        "obsidian-brain"
      ]
    }
  }
}
```

See [Claude Code MCP docs](https://docs.anthropic.com/en/docs/claude-code/mcp) for more details.
</details>

<details>
<summary><strong>OpenAI Codex CLI</strong></summary>

Add the server using the CLI:

```bash
codex mcp add obsidian-brain \
  -- uvx --from git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP obsidian-brain
```

Or manually edit `~/.codex/config.toml`:

```toml
[mcp_servers.obsidian-brain]
command = "uvx"
args = ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"]
```

See [Codex MCP docs](https://developers.openai.com/codex/mcp/) for more details.
</details>

<details>
<summary><strong>Windsurf</strong></summary>

Edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "obsidian-brain": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"]
    }
  }
}
```

See [Windsurf MCP docs](https://docs.windsurf.com/windsurf/cascade/mcp) for more details.
</details>

<details>
<summary><strong>VS Code (GitHub Copilot)</strong></summary>

Add to `.vscode/mcp.json` (project) or global settings:

```json
{
  "servers": {
    "obsidian-brain": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"]
    }
  }
}
```

See [VS Code MCP docs](https://code.visualstudio.com/docs/copilot/chat/mcp-servers) for more details.
</details>

<details>
<summary><strong>Zed</strong></summary>

Add to `~/.config/zed/settings.json` (Linux) or `~/Library/Application Support/Zed/settings.json` (macOS):

```json
{
  "context_servers": {
    "obsidian-brain": {
      "command": {
        "path": "uvx",
        "args": ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"]
      }
    }
  }
}
```

See [Zed MCP docs](https://zed.dev/docs/ai/mcp) for more details.
</details>

<details>
<summary><strong>OpenCode</strong></summary>

Add to `opencode.json` in your project:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "obsidian-brain": {
      "type": "local",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"],
      "enabled": true
    }
  }
}
```

See [OpenCode MCP docs](https://opencode.ai/docs/mcp-servers/) for more details.
</details>

<details>
<summary><strong>Direct CLI Usage</strong></summary>

```bash
# Run directly (for testing)
uvx --from git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP obsidian-brain

# Or install as a tool
uv tool install git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP
obsidian-brain
```
</details>

---

## Configuration

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `OBSIDIAN_CLI_PATH` | | auto-detected | Obsidian CLI executable path; set this to point at the binary explicitly |
| `OBSIDIAN_VAULT` | | see vault resolution below | Vault folder name or id (not a filesystem path) to pass as the CLI's `vault=` argument |

The CLI resolves the target vault in this order:
1. The `vault=` argument, which the server sends when `OBSIDIAN_VAULT` is set.
2. The calling process's CWD, if it is inside a registered vault.
3. The most recently focused open vault window in Obsidian.
4. Otherwise the command fails with `Vault not found.`.

If `OBSIDIAN_VAULT` is unset, you **must** have the vault open in Obsidian. The reliable option is to set it to the vault's folder name; Obsidian opens that vault's window on demand. A vault id from Obsidian's registry also works — the registry lives at `~/.config/obsidian/obsidian.json` on Linux (or `$XDG_CONFIG_HOME/obsidian/obsidian.json`), `~/Library/Application Support/obsidian/obsidian.json` on macOS, and `%APPDATA%\obsidian\obsidian.json` on Windows.

Failures are reported as MCP tool errors in plain words: Obsidian not running, CLI disabled, vault not found, note not found, a note that already exists, a heading that is missing, a call that is too large. An error names the path, heading, link or tag in question, but never contains note content or the code sent to Obsidian.

Timeouts: every call is bounded (20 s). A read, a search or an idempotent edit (`update_tags`, `write_note` with `overwrite=true`) that times out is retried once, so the worst case is twice the timeout. Every other write (`append_to_note`, `append_to_daily`, `add_link`, `write_note` without `overwrite`, `delete_note`) is never retried, and its timeout error says the write may have happened: read the note before trying again. The `Received CLI command [...]` lines Obsidian echoes to stdout when several CLI calls run at once are stripped from the output.

### Troubleshooting

- `Obsidian's command line interface is disabled` — turn on **Command line interface** in Settings > General > Advanced.
- `Vault not found` — set `OBSIDIAN_VAULT` to the vault's folder name or id, or open the vault in Obsidian.
- `Obsidian is not running` — start the Obsidian desktop app and wait for the vault to load.
- `Obsidian CLI not found` — register the CLI (see Prerequisites) or set `OBSIDIAN_CLI_PATH`.
- A write fails with a size error — one call carries at most about 900 KB of text (the code travels as a command-line argument). Split the content.

Onboarding, memories and the knowledge base live in a visible `Obsidian Brain/` folder inside the vault (Obsidian does not index dot-folders). The vault profile is a fenced YAML block in `Obsidian Brain/config.md`, so it renders in Obsidian and can be edited by hand; `run_onboarding` will not overwrite your edits unless you pass `force=true`.

---

## MCP Resources

| Resource | Type | Description |
|----------|------|-------------|
| `vault://files` | JSON | Every file with `path`, `extension`, `size` and `modified`; Markdown entries include their note URI |
| `vault://note/{+path}` | Markdown | Exact text of a note. Slashes may be sent as-is (`vault://note/Projects/Plan.md`) or encoded (`%2F`) |
| `vault://tags` | JSON | Every tag with its occurrence count, as Obsidian counts them |
| `vault://stats` | JSON | Note, folder (all depths), tag, link and orphan counts, not counting `Obsidian Brain/` |
| `vault://knowledge` | Markdown | The generated knowledge base |

Resources read the vault on every request, so there is nothing to refresh. A missing note or knowledge base is a protocol error, not a body that looks like data. An IDE's `@` picker is a host feature; no MCP server change can force resources into it. Use the client's MCP resource browser, or read `vault://files` and then a returned note URI.

---

## Available Tools

Every tool returns structured data, has typed and described parameters, and carries MCP annotations (read-only, destructive, idempotent) so clients can decide what to confirm. Failures come back as MCP tool errors with a short, actionable message.

### Notes

| Tool | Description |
|------|-------------|
| `list_vault_files` | List files under a folder, recursively, one page at a time (`limit`, `offset`; returns `total`) |
| `get_note` | Read a note: exact text, frontmatter, tags (inline too), links and headings |
| `write_note` | Create a note, or replace one with `overwrite=true`. Content is stored verbatim: nothing is added to it |
| `append_to_note` | Append atomically, at the end or at the end of a named heading's section |
| `delete_note` | Move a note to Obsidian's trash (`permanent=true` deletes for good) |

### Links, Tags and Search

| Tool | Description |
|------|-------------|
| `get_links` | Backlinks and outgoing links of a note, 1-3 hops deep |
| `add_link` | Append a `[[wikilink]]` to a note; the target is resolved like Obsidian does and the call is idempotent |
| `update_tags` | Add or remove frontmatter tags without touching the rest of the file |
| `list_all_tags` | Every tag (inline and frontmatter) with Obsidian's occurrence counts |
| `get_notes_by_tag` | Notes with a tag, nested tags included by default |
| `search_content` | Search with Obsidian's own syntax (`path:`, `tag:`, quotes), with a result limit |

### Daily Notes

| Tool | Description |
|------|-------------|
| `get_daily_note` | Read today's or a given date's daily note without creating it |
| `append_to_daily` | Append to the daily note of any date, creating it from your template and any missing heading section; optional `HH:MM` timestamp, tags and links |

### Memory, Onboarding and Knowledge Base

| Tool | Description |
|------|-------------|
| `get_vault_config` | Start here: onboarding state, the vault profile, memory count and knowledge base status |
| `run_onboarding` | Profile the vault (PARA/Zettelkasten, tags, naming, frontmatter) into `Obsidian Brain/config.md` and two starter memories. Existing files are kept unless `force=true` |
| `list_memories` | List cross-session memories with type and timestamps |
| `read_memory` / `write_memory` / `delete_memory` | Read, create or replace, and trash a memory. Names match by slug (`Project X` = `project_x`); a different spelling of an existing slug is refused rather than overwriting |
| `build_knowledge_base` | Generate `Obsidian Brain/knowledge-base.md`: folder tree, tag taxonomy, hub notes, link patterns, orphans |

Memories live in `Obsidian Brain/memories/` as ordinary notes, so you can read and edit them in Obsidian; notes you add there by hand show up in `list_memories`.

### Behaviour notes

- **Paths** are vault-relative with forward slashes and are Unicode NFC-normalised on input, so `Café.md` typed with a combining accent and with a precomposed `é` is one note. `write_note` appends `.md` unless the path ends in a file type Obsidian opens (`md`, `canvas`, `base`, images, audio, video, `pdf`; case-insensitive): `Learning Node.js` becomes `Learning Node.js.md`, and `data.json` becomes `data.json.md`.
- **`update_tags`** rewrites only the `tags` entry of the frontmatter, as a block list; every other frontmatter line (comments, quoting, key order) and the whole body stay byte-identical. Inline `#tags` in the body are never edited.
- **`list_all_tags`** reports `occurrences`, counted the way Obsidian's tag pane counts them (a tag used twice in one note counts twice); `vault://tags` carries the same counts.
- **`search_content`** caps each matching line at 300 characters around the match (`…` marks the cut), so one very long line cannot flood the result.
- **`write_memory`** on an existing memory reads, then rewrites the whole file: two concurrent writes to the same memory are last-writer-wins, and comments inside the memory's frontmatter are dropped (the values are kept).
- **Daily tools** (`get_daily_note`, `append_to_daily`) use the **Daily notes** core plugin's folder, format and template, so that plugin must be enabled; the Periodic Notes community plugin is not read.

### Upgrading from 0.1

Version 0.2.0 needs `mcp>=2.3` and cuts the tool surface from 29 to 20. There are no aliases for the removed names.

| 0.1 tool | 0.2 replacement |
|----------|-----------------|
| `create_note`, `update_note` | `write_note` (`overwrite=true` to replace). Nothing is added to the content any more: no frontmatter, H1 or tags |
| `add_tags`, `remove_tags` | `update_tags(path, add, remove)` |
| `get_backlinks`, `get_outgoing_links`, `get_linked_notes` | `get_links(path, direction, depth)` |
| `add_backlink` | `add_link` |
| `create_daily_entry` | `append_to_daily(..., timestamp=true, tags, links)` |
| `edit_memory` | `write_memory` (replaces the body of an existing memory) |
| `check_onboarding_status`, `get_knowledge_base_status` | `get_vault_config` |
| `create_vault_knowledge_base` | `build_knowledge_base` |
| `refresh_vault_structure` | none: nothing is cached, so there is nothing to refresh |

`delete_note` now moves to the trash unless `permanent=true`. The `vault://structure` resource is gone; use `vault://files`, `vault://tags` and `vault://stats`. The other 0.1 tools keep their names.

---

## Development

```bash
# Clone the repository
git clone https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP.git
cd The-Obsidian-Brain-MCP

# Install dependencies
uv sync --extra dev

# Run the server from the package module
uv run python -m obsidian_brain.server

# Run the unit tests (no Obsidian needed)
uv run pytest

# Run the live tests against a disposable vault (name must contain "testvault")
OBSIDIAN_TEST_VAULT=my-testvault uv run pytest -m obsidian

# Lint, format and type-check
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

The server is built on `mcp.server.mcpserver.MCPServer` from the official MCP Python SDK, version 2.3 (`mcp>=2.3,<3`). Every vault operation is a snippet of JavaScript run inside Obsidian through `obsidian eval` (see [SPECIFICATION.md](SPECIFICATION.md) for the architecture).

---

## Contributing

Contributions are welcome! Whether it's bug fixes, new features, or documentation improvements.

---

## License

[MIT](LICENSE) -- Build something amazing with it.

---

<p align="center">
  <strong>Stop losing your best ideas to chat history.</strong><br/>
  <em>Let your AI and your vault think together.</em>
</p>
