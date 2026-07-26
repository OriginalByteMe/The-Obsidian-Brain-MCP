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

As ideas flow, your AI captures them in a scratch note. When you land on a good angle, it moves the content to your `Writing/Drafts` folder, adds relevant tags, and links to your research notes on `[[AI Tools]]` and `[[Personal Productivity]]`.

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
| **Smart Linking** | Automatically discover and create backlinks, traverse your knowledge graph |
| **Tag Intelligence** | Add, remove, and search by tags across your entire vault |
| **Text Search** | Full-text search across your entire vault |
| **Daily Notes** | Seamless integration with daily notes |
| **Vault Onboarding** | AI learns your vault's structure, conventions, and patterns |
| **Persistent Memory** | Cross-session context that remembers previous interactions |
| **Knowledge Base** | Generate comprehensive vault overviews for deep AI understanding |

---

<a id="installation"></a>

## Prerequisites

1. **Obsidian 1.12.4+** with the CLI enabled:
   - Open **Obsidian Settings > General > Command line interface**
   - Enable the CLI toggle
   - Keep the Obsidian desktop app running while the server uses the CLI
   - The `obsidian` command must be on your PATH
   - Alternatively, set the `OBSIDIAN_CLI_PATH` environment variable to the full path of the `obsidian` binary
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
| `OBSIDIAN_CLI_PATH` | | auto-detected | Obsidian CLI executable path when it is not on `PATH` |
| `OBSIDIAN_VAULT` | | CLI default/active vault | Exact Obsidian vault name (not a filesystem path) |

The server discovers the CLI lazily. Set `OBSIDIAN_CLI_PATH` only for a non-standard executable location. Set `OBSIDIAN_VAULT` when the CLI should target a specific vault; otherwise Obsidian's default/active vault is used.

> **Note:** The Obsidian CLI always exits 0 and never writes to stderr, even
> on failure -- it reports errors as plain text on stdout (e.g.
> `Error: File "Note.md" not found.`). This server classifies failures by
> parsing that stdout text rather than relying on the exit code.

Onboarding writes its vault profile to the visible `Obsidian Brain/config.yml` path.

---

## MCP Resources

| Resource | Description |
|----------|-------------|
| `vault://files` | Cached JSON index of every vault file, with its path and whether it is text-readable; Markdown entries also include a note URI |
| `vault://note/{path}` | Parameterized Markdown note reader; use the percent-encoded URIs included for readable entries in `vault://files` |
| `vault://structure` | Cached vault structure and note metadata |
| `vault://tags` | Cached tag counts |
| `vault://stats` | Cached vault statistics |
| `vault://knowledge` | Persistent Markdown knowledge base |

Call `refresh_vault_structure` before using the cached resources and again when vault changes need to appear. It populates the cached vault structure, including the all-file index and Markdown note metadata. Non-Markdown files are indexed but marked unreadable and do not receive a `vault://note/{path}` URI; the note resource is Markdown-only.

MCP resource discovery and reads are what this server can guarantee. An IDE's `@` picker is a host feature; no MCP server change can force resources into or customize that UI. Use the client's MCP resource browser when available, or read `vault://files` and then a returned note URI.

---

## Available Tools

### Vault Operations

| Tool | Description |
|------|-------------|
| `list_vault_files` | List files at any path, recursively (the CLI never returns folders) |
| `get_note` | Read note content, tags, links, and frontmatter |
| `create_note` | Create notes with tags and validated backlinks |
| `update_note` | Replace note content entirely |
| `append_to_note` | Append content, optionally under a specific heading |
| `delete_note` | Remove a note from your vault |
| `refresh_vault_structure` | Rebuild the cached vault structure |

### Link Operations

| Tool | Description |
|------|-------------|
| `add_backlink` | Add a `[[wikilink]]` to any note |
| `get_backlinks` | Find all notes that link TO a specific note |
| `get_outgoing_links` | Find all notes a specific note links TO |
| `get_linked_notes` | Traverse the link graph (1-3 hops deep) |

### Tag Operations

| Tool | Description |
|------|-------------|
| `add_tags` | Add tags to a note's frontmatter |
| `remove_tags` | Remove tags from a note |
| `list_all_tags` | Get all tags in your vault with usage counts |
| `get_notes_by_tag` | Find all notes with a specific tag |

### Search Operations

| Tool | Description |
|------|-------------|
| `search_content` | Full-text search across your entire vault |

### Daily Notes

| Tool | Description |
|------|-------------|
| `get_daily_note` | Retrieve today's or a specific date's daily note |
| `append_to_daily` | Add content to your daily note |
| `create_daily_entry` | Create timestamped entries with tags and links |

### Knowledge & Memory

| Tool | Description |
|------|-------------|
| `create_vault_knowledge_base` | Generate a comprehensive vault overview |
| `get_knowledge_base_status` | Check if knowledge base exists and when updated |
| `check_onboarding_status` | See if vault has been analyzed |
| `run_onboarding` | Analyze vault structure and create configuration |
| `list_memories` | List all stored cross-session memories |
| `read_memory` / `write_memory` | Read or write persistent memory |
| `edit_memory` / `delete_memory` | Modify or remove memories |

---

## Development

```bash
# Clone the repository
git clone https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP.git
cd The-Obsidian-Brain-MCP

# Install dependencies
uv sync --dev

# Run the server from the package module
uv run python -m obsidian_brain.server

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

The project uses `mcp.server.fastmcp.FastMCP` from the official MCP Python SDK v1 line and pins `mcp<2`. MCP v2 remains alpha, while standalone `fastmcp` v4 requires the `mcp==2.0.0b2` prerelease.

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
