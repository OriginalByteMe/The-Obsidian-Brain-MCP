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

## 🧠 The Problem

You've been there. Hours deep in a coding session or research rabbit hole with your AI assistant. Discoveries made. Problems solved. Concepts finally clicked.

Then you close the chat.

**Gone.**

All those insights, explanations, and breakthroughs scattered across a poorly saved claude code sessions or chatgpt chats history. Meanwhile, your Obsidian vault sits waiting, ready to connect ideas, but completely disconnected from where your best thinking actually happens.

## ✨ The Solution

**Obsidian Brain MCP** creates a living bridge between your AI assistant and your Obsidian vault. Your LLM doesn't just *respond*—it *remembers*, *organizes*, and *connects*.

```
💬 AI Conversation  ←→  🧠 Obsidian Brain MCP  ←→  📚 Your Vault
```

Now your assistant can:
- 📝 **Capture insights** directly into your vault as you discover them
- 🔗 **Build connections** by linking new notes to existing knowledge
- 🔍 **Search your mind** to find relevant notes you forgot you had
- 📊 **Understand your graph** and help you see patterns in your thinking
- ✍️ **Match your style** by learning from how you actually write

---

## 🎬 See It In Action

<p align="center">
  <img src="assets/ObsidianMCPDemo.gif" alt="Obsidian Brain MCP Demo" width="800" />
</p>

<p align="center">
  <em>Creating notes, building connections, and searching your vault—all through natural conversation.</em>
</p>

---

## 💡 Use Cases

<details>
<summary>🎓 <strong>Learning & Research</strong></summary>

> *"Explain how React Server Components work"*

As your AI explains the concept, ask it to save key insights directly to your vault. It creates a note, links it to your existing `[[React]]` and `[[Frontend Architecture]]` notes, and tags it `#learning #react #server-components`.

Next week when you're debugging an RSC issue, your AI can search your vault and remind you of the mental model you built together.
</details>

<details>
<summary>💻 <strong>Coding Sessions</strong></summary>

> *"Help me debug this authentication flow"*

After 2 hours of debugging, you finally crack it. Instead of losing that hard-won knowledge, ask your AI to document the solution. It creates a note under `Development/Debugging` with:
- The symptoms you encountered
- The root cause
- The fix
- Links to related notes like `[[Auth Middleware]]` and `[[JWT Tokens]]`

Future you will thank present you.
</details>

<details>
<summary>✍️ <strong>Writing & Content Creation</strong></summary>

> *"Let's brainstorm ideas for my blog post on AI productivity"*

As ideas flow, your AI captures them in a scratch note. When you land on a good angle, it moves the content to your `Writing/Drafts` folder, adds relevant tags, and links to your research notes on `[[AI Tools]]` and `[[Personal Productivity]]`.

Your vault becomes your writing partner's memory.
</details>

<details>
<summary>📋 <strong>Meeting Notes & Action Items</strong></summary>

> *"Add today's standup notes to my daily note"*

Your AI appends a timestamped entry to today's daily note with discussion points, decisions made, and action items—all properly tagged and linked to relevant project notes.

```markdown
## 🗓️ 10:30 - Standup
- Discussed [[Project Alpha]] timeline
- Decision: Push launch to Q2 #decision
- Action: Review PR #142 by EOD #todo
```
</details>

<details>
<summary>🧠 <strong>Personal Knowledge Management</strong></summary>

> *"What do I know about distributed systems?"*

Your AI searches your vault, finds 23 related notes across `Learning/`, `Projects/`, and `Books/`, and synthesizes a summary of your knowledge landscape. It identifies gaps and suggests areas to explore further.

Your scattered notes become a queryable knowledge base.
</details>

<details>
<summary>📚 <strong>Book & Article Notes</strong></summary>

> *"I just finished reading 'Thinking in Systems' - help me capture the key ideas"*

As you discuss the book, your AI creates structured literature notes in your preferred format, extracts key concepts into atomic notes, and weaves them into your existing knowledge graph with relevant backlinks.

Every book you read strengthens your second brain.
</details>

---

## 🚀 Features

| Feature | Description |
|---------|-------------|
| 🗂️ **Full Vault Access** | Read, create, update, and organize notes without leaving your conversation |
| 🔗 **Smart Linking** | Automatically discover and create backlinks, traverse your knowledge graph |
| 🏷️ **Tag Intelligence** | Add, remove, and search by tags across your entire vault |
| 🔍 **Powerful Search** | Full-text search, Dataview queries, and complex filtering |
| 📅 **Daily Notes** | Seamless integration with daily, weekly, and periodic notes |
| 🧭 **Vault Onboarding** | AI learns your vault's structure, conventions, and patterns |
| 💾 **Persistent Memory** | Cross-session context that remembers previous interactions |
| 📊 **Knowledge Base** | Generate comprehensive vault overviews for deep AI understanding |
| 🔌 **Claude Code Plugin** | Install as a plugin with skills, hooks, and brag doc tracking |

---

## 🔌 Claude Code Plugin

Obsidian Brain is also available as a **Claude Code plugin** that adds proactive knowledge capture to your coding sessions.

### Plugin Installation

```bash
# Add the marketplace
/plugin marketplace add OriginalByteMe/The-Obsidian-Brain-MCP

# Install the plugin
/plugin install obsidian-brain
```

### Available Skills

| Skill | Description |
|-------|-------------|
| `/document-it [topic]` | Document a function, decision, or concept as a structured vault note |
| `/capture-learning [focus]` | Capture session learnings as a structured learning note |
| `/review-session` | Summarize the session and log to daily note |
| `/brain-status` | Show vault connection, today's activity, and configuration |
| `/brain-config [setting] [value]` | View or change plugin autonomy settings |

### Lifecycle Hooks

The plugin automatically:
- **Session Start**: Loads vault context and today's daily note summary
- **Periodic Check-in**: Reminds to capture notes after a configurable interval (default: 30 min)
- **Session End**: Evaluates if the session contained noteworthy learnings

### Autonomy Configuration

Control how proactive the plugin is with `/brain-config`:

| Setting | Default | Options |
|---------|---------|---------|
| `autonomy.session_start_context` | `silent` | `silent`, `prompt`, `disabled` |
| `autonomy.session_end_learning_capture` | `prompt` | `silent`, `prompt`, `disabled` |
| `autonomy.session_end_daily_log` | `silent` | `silent`, `prompt`, `disabled` |
| `autonomy.brag_doc_update` | `prompt` | `silent`, `prompt`, `disabled` |
| `autonomy.periodic_checkin` | `prompt` | `silent`, `prompt`, `disabled` |

---

<a id="installation"></a>

## 📦 Installation

### Prerequisites

1. **Obsidian** with the [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) plugin enabled
2. **uv** package manager → [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

### Quick Start

Add to your MCP client configuration:

<details>
<summary>🖱️ <strong>Cursor</strong></summary>

Add to `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project):

```json
{
  "mcpServers": {
    "obsidian-brain": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"],
      "env": {
        "OBSIDIAN_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

See [Cursor MCP docs](https://docs.cursor.com/context/model-context-protocol) for more details.
</details>

<details>
<summary>📍 <strong>Claude Desktop / Claude Code</strong></summary>

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
      ],
      "env": {
        "OBSIDIAN_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

See [Claude Code MCP docs](https://docs.anthropic.com/en/docs/claude-code/mcp) for more details.
</details>

<details>
<summary>🤖 <strong>OpenAI Codex CLI</strong></summary>

Add the server using the CLI:

```bash
codex mcp add obsidian-brain \
  --env OBSIDIAN_API_KEY=your-api-key-here \
  -- uvx --from git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP obsidian-brain
```

Or manually edit `~/.codex/config.toml`:

```toml
[mcp_servers.obsidian-brain]
command = "uvx"
args = ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"]

[mcp_servers.obsidian-brain.env]
OBSIDIAN_API_KEY = "your-api-key-here"
```

See [Codex MCP docs](https://developers.openai.com/codex/mcp/) for more details.
</details>

<details>
<summary>💨 <strong>Windsurf</strong></summary>

Edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "obsidian-brain": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"],
      "env": {
        "OBSIDIAN_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

See [Windsurf MCP docs](https://docs.windsurf.com/windsurf/cascade/mcp) for more details.
</details>

<details>
<summary>🆚 <strong>VS Code (GitHub Copilot)</strong></summary>

Add to `.vscode/mcp.json` (project) or global settings:

```json
{
  "servers": {
    "obsidian-brain": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"],
      "env": {
        "OBSIDIAN_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

See [VS Code MCP docs](https://code.visualstudio.com/docs/copilot/chat/mcp-servers) for more details.
</details>

<details>
<summary>⚡ <strong>Zed</strong></summary>

Add to `~/.config/zed/settings.json` (Linux) or `~/Library/Application Support/Zed/settings.json` (macOS):

```json
{
  "context_servers": {
    "obsidian-brain": {
      "command": {
        "path": "uvx",
        "args": ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"],
        "env": {
          "OBSIDIAN_API_KEY": "your-api-key-here"
        }
      }
    }
  }
}
```

See [Zed MCP docs](https://zed.dev/docs/ai/mcp) for more details.
</details>

<details>
<summary>🔓 <strong>OpenCode</strong></summary>

Add to `opencode.json` in your project:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "obsidian-brain": {
      "type": "local",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP", "obsidian-brain"],
      "env": {
        "OBSIDIAN_API_KEY": "your-api-key-here"
      },
      "enabled": true
    }
  }
}
```

See [OpenCode MCP docs](https://opencode.ai/docs/mcp-servers/) for more details.
</details>

<details>
<summary>🖥️ <strong>Direct CLI Usage</strong></summary>

```bash
# Run directly (for testing)
OBSIDIAN_API_KEY=your-key uvx --from git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP obsidian-brain

# Or install as a tool
uv tool install git+https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP
OBSIDIAN_API_KEY=your-key obsidian-brain
```
</details>

### 🔑 Getting Your API Key

1. Open **Obsidian Settings**
2. Navigate to **Community Plugins → Local REST API**
3. Click **Copy API Key**

---

## ⚙️ Configuration

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `OBSIDIAN_API_KEY` | ✅ | — | API key from Local REST API plugin |
| `OBSIDIAN_URL` | | — | Full URL override (e.g., `http://localhost:27124`) |
| `OBSIDIAN_HOST` | | `127.0.0.1` | API host (ignored if URL is set) |
| `OBSIDIAN_PORT` | | `27124` | API port (ignored if URL is set) |
| `OBSIDIAN_VERIFY_SSL` | | `false` | Verify SSL certificate |

<details>
<summary>📋 <strong>Example Configurations</strong></summary>

**Plain HTTP (reverse proxy):**
```json
{ "env": { "OBSIDIAN_API_KEY": "...", "OBSIDIAN_URL": "http://localhost:8080" } }
```

**Docker on Mac/Windows:**
```json
{ "env": { "OBSIDIAN_API_KEY": "...", "OBSIDIAN_HOST": "host.docker.internal" } }
```

**Custom port:**
```json
{ "env": { "OBSIDIAN_API_KEY": "...", "OBSIDIAN_PORT": "27125" } }
```
</details>

---

## 🛠️ Available Tools

### 📁 Vault Operations

| Tool | Description |
|------|-------------|
| `list_vault_files` | List files and folders at any path |
| `get_note` | Read note content, tags, links, and frontmatter |
| `create_note` | Create notes with tags and validated backlinks |
| `update_note` | Replace note content entirely |
| `append_to_note` | Append content, optionally under a specific heading |
| `delete_note` | Remove a note from your vault |
| `refresh_vault_structure` | Rebuild the cached vault structure |

### 🔗 Link Operations

| Tool | Description |
|------|-------------|
| `add_backlink` | Add a `[[wikilink]]` to any note |
| `get_backlinks` | Find all notes that link TO a specific note |
| `get_outgoing_links` | Find all notes a specific note links TO |
| `get_linked_notes` | Traverse the link graph (1-3 hops deep) |

### 🏷️ Tag Operations

| Tool | Description |
|------|-------------|
| `add_tags` | Add tags to a note's frontmatter |
| `remove_tags` | Remove tags from a note |
| `list_all_tags` | Get all tags in your vault with usage counts |
| `get_notes_by_tag` | Find all notes with a specific tag |

### 🔍 Search Operations

| Tool | Description |
|------|-------------|
| `search_content` | Full-text search across your entire vault |
| `search_advanced` | Dataview DQL queries (requires Dataview plugin) |
| `search_jsonlogic` | Complex filtering with JsonLogic syntax |

### 📅 Daily & Periodic Notes

| Tool | Description |
|------|-------------|
| `get_daily_note` | Retrieve today's or a specific date's daily note |
| `append_to_daily` | Add content to your daily note |
| `create_daily_entry` | Create timestamped entries with tags and links |
| `get_periodic_note` | Access weekly, monthly, quarterly, or yearly notes |

### 🧠 Knowledge & Memory

| Tool | Description |
|------|-------------|
| `create_vault_knowledge_base` | Generate a comprehensive vault overview |
| `get_knowledge_base_status` | Check if knowledge base exists and when updated |
| `check_onboarding_status` | See if vault has been analyzed |
| `run_onboarding` | Analyze vault structure and create configuration |
| `list_memories` | List all stored cross-session memories |
| `read_memory` / `write_memory` | Read or write persistent memory |
| `edit_memory` / `delete_memory` | Modify or remove memories |

### 🔌 Session & Plugin (Plugin Mode)

| Tool | Description |
|------|-------------|
| `get_brain_config` | Read plugin configuration (autonomy + plugin settings) |
| `update_brain_config` | Update a configuration value with dot-notation key |
| `get_session_state` | Get current session tracking state |
| `record_session_activity` | Record an activity for deduplication and logging |
| `append_to_brag_doc` | Add an entry to the brag document |

---

## 🏗️ Development

```bash
# Clone the repository
git clone https://github.com/OriginalByteMe/The-Obsidian-Brain-MCP.git
cd The-Obsidian-Brain-MCP

# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

---

## 🤝 Contributing

Contributions are welcome! Whether it's bug fixes, new features, or documentation improvements.

---

## 📄 License

[MIT](LICENSE) — Build something amazing with it.

---

<p align="center">
  <strong>Stop losing your best ideas to chat history.</strong><br/>
  <em>Let your AI and your vault think together.</em>
</p>
