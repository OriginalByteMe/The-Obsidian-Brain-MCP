# The Obsidian Brain MCP - Technical Specification

> **Version**: 0.2.0
> **Status**: Active
> **Last Updated**: 2026-11-23

## Overview

An MCP (Model Context Protocol) server that lets AI agents work with an Obsidian vault through the running Obsidian app. Every operation is a short JavaScript snippet that Obsidian executes against its own plugin API (`app.vault`, `app.metadataCache`, `app.fileManager`), delivered with the [Obsidian CLI](https://obsidian.md/) `eval` command. The server therefore sees notes the way Obsidian does: the same links, tags, headings and frontmatter, with no second parser to drift out of date.

### Primary Use Cases

1. **Research Synthesis**: Create well-linked notes from research with proper backlinks and tags
2. **Daily Note Management**: Capture information to the daily note of any date
3. **Knowledge Traversal**: Navigate the vault's link graph to explore connected concepts
4. **Cross-session Memory**: Keep onboarding results, conventions and learnings in the vault itself

---

## Architecture

```
MCP client <-stdio-> server.py -> tools/*.py, resources.py
                                      |
                                  vault.py   class Vault: one method per vault operation
                                      |
                                  obsidian.py   class ObsidianCLI: run the CLI, eval JSON in/out
                                      |
                       `obsidian [vault=V] eval code="<js>"`  (subprocess, list-form argv)
                                      |
                             running Obsidian app (plugin API)
```

```
src/obsidian_brain/
  __init__.py       __version__ (read from package metadata; pyproject.toml is the source)
  server.py         MCPServer, instructions, main()
  obsidian.py       transport: CLI discovery, subprocess runner, eval envelope
  vault.py          Vault: every vault operation as JavaScript over eval, typed returns
  models.py         pydantic models shared by Vault and the tools
  exceptions.py     ObsidianError(ToolError) hierarchy
  memory.py         memory slugs, frontmatter block helpers, Obsidian Brain/ paths
  onboarding.py     vault analysis and config / starter-memory rendering (pure)
  knowledge.py      vault statistics and knowledge base rendering (pure)
  resources.py      vault:// resources
  tools/
    notes.py        notes, links, tags, search
    daily.py        daily notes
    memory.py       list/read/write/delete_memory
    onboarding.py   get_vault_config, run_onboarding
    knowledge.py    build_knowledge_base
tests/              unit tests (no Obsidian) and live tests (-m obsidian)
```

### Transport (`obsidian.py`)

`ObsidianCLI(cli_path=None, vault=None, timeout=20.0, max_evals=1, reply_grace=2.0)` locates the binary (`OBSIDIAN_CLI_PATH`, then `obsidian-cli`, then `obsidian` on `PATH`; the Electron app launcher is rejected in favour of the bundled `obsidian-cli`) and runs it with list-form argv, never a shell. `OBSIDIAN_VAULT` selects the vault.

- **Subprocess hygiene**: stdin is `/dev/null` (the CLI would otherwise consume the MCP server's stdin), every call has a timeout, and a timed-out or cancelled call kills and reaps its child.
- **Cold start**: one retry when the CLI answers `Command "<cmd>" not found` while Obsidian is still starting.
- **Failure classification**: CLI not found, Obsidian not running (exit 1 and `The CLI is unable to find Obsidian`), CLI disabled, vault not found, and launcher start-up output each map to a typed error with an actionable message. Error text carries the command name and at most 500 characters of CLI output. It never contains note content, the `eval` code or its payload; errors raised inside the snippets do name the path, heading, link or tag in question (`Note not found: Projects/Plan.md`, `Heading not found: Tasks`).
- **Retry after timeout**: a call that hits its timeout is retried once, but only when it is idempotent: every read, `search`, `update_tags`, `replace_body` (the `write_memory` update) and `write_note` with `overwrite=true` (the worst case is twice the timeout). A write that is not idempotent (`append`, `append_unless_linked`, `append_daily`, `delete`, `write_note` without `overwrite`) is never retried, and its timeout error says the write may have happened. For an `eval` this is the last resort: a reply Obsidian never sends is recovered long before the timeout (next bullets), so the timeout is only reached when the window answers nothing at all, or the call itself runs longer than the timeout. `search:context` is not an `eval`, so it still waits the whole timeout for a reply that never comes.
- **Echo lines**: when several CLI processes run at once Obsidian prints `Received CLI command [...]` lines, including other processes' arguments, to stdout. They are stripped before the output is classified or parsed. This server sends one `eval` at a time (next bullet), so it only sees them when another client is using the same vault.
- **One `eval` at a time**: the `eval` calls of one `ObsidianCLI` (one per vault) wait for each other; `max_evals` (default `MAX_EVALS_IN_FLIGHT = 1`) is the bound. The wait for a turn does not count against the timeout, a call retried after a timeout keeps its turn, and other commands (`search:context`) never wait. The reason is a leak in Obsidian 1.15's `eval` command: it replaces `console.log`, `console.warn` and `console.error` for the length of each call and then puts back what it found. When two calls overlap and the earlier one ends first, the later one puts back the earlier one's replacement, which then stays installed for good and keeps every later console message of the window (each CLI command logs its whole argv) until the window reloads. Every overlap that ends out of order adds one such replacement, so the memory held per call grows with the number of them. A minimized or hidden window overlaps the most calls. Measured on one, as retained JS heap after a forced garbage collection, over 1,075 server calls (900 `get_note`, 150 at a time, then a burst of writes): the first version of this transport (the whole helper code in every call, up to 150 calls at once) left 13 to 33 MB behind with 4 to 9 replacements (6 runs); short calls two or four at a time left 4 to 7 MB with 6 to 15 (6 runs); short calls one at a time left 1.9 to 2.2 MB with none (8 runs), so the bound is 1. The price is throughput: 900 `get_note` calls took about 6 s instead of 4.6 s, 7 ms per call instead of 5. Other processes that send `eval` to the same vault can still overlap with this server's calls; the short calls below keep what that leaves behind small.
- **Install once**: `eval` sends a snippet to a window once and calls it afterwards. The first call is one expression that makes sure `window.__brain` holds this server's runner (`{rev, fns, run}`, `rev` being a hash of the runner's text; a window with another `rev` has it replaced), stores the body as `fns[key]` (`key` is a hash of the runner and the body) and calls `run(key, payload, id)`. Later calls send only `window.__brain?.fns['<key>'] ? window.__brain.run('<key>', <payload>, '<id>') : <missing>`, 134 bytes plus the payload instead of 7 to 11 KB of helper code that Obsidian would compile and log each time. A window that does not hold the function (it was reloaded, or another server version replaced the runner) answers `{"ok":false,"missing":true}`, and the server sends the first-call form once more. The set of keys already sent is only a hint for skipping the first-call form, so it never matters if it is wrong. A body must be a constant (data goes in the payload), or every value would install another function.
- **Lost replies**: Obsidian runs some `eval` calls and never answers them, and the CLI process then waits for the reply forever. Counted inside the window with a counter the call increments, 5 of 4,500 sequential calls on two windows were lost (about 1 in 900, more under load); every one of the five had run, none was answered late (waited 25 s), and none had failed to arrive. Answered calls took a median of 11 to 22 ms, 99% under 0.35 s and at most 0.87 s. Left alone, a lost reply makes a non-idempotent write fail with "may have carried the command out" even though it ran, and stalls every `eval` queued behind it for the whole timeout. So every `eval` carries a fresh request id (16 hex characters) and the runner keeps what became of each id in `window.__brainReqs` (`running`, or `done` with the answer; it outlives a replaced runner). An id the log already knows never starts. A call that has no reply after `reply_grace` (2 s: well above the slowest answered call measured, and asking early costs one short call) asks the window about its id with a second `eval`, which says:
  - **done**: the stored answer is used as if the CLI had printed it, and the hung CLI child is killed and reaped. The call is not run again, whether or not it is idempotent.
  - **running**: the call is only slow. It is waited for and asked about again every `reply_grace` until the timeout, never sent twice.
  - **cancelled**: the window had never seen the id, and the question itself recorded it as cancelled, so the original can never start, even if it reaches Obsidian later (the live suite delivers one 2 s late and checks it is refused). The call is sent again under a new id, which is safe for a write too. The new send keeps the call's deadline and its turn.

  The question is a short `eval` of its own: it does not take a turn (the call that holds the turn is the one asking), questions are asked one at a time, and one that gets no reply within `reply_grace` is asked again (asking twice gives the same answer). It runs while the call it is about is still running or long finished, and it ends first, so the two end in the order they began: it leaves no console replacement behind (see the previous bullet; `TestLostReply` counts them after a burst that triggers six recoveries and after a call that is asked about while it runs). The log is bounded: 128 entries, finished ones dropped after 2 minutes (one still running is never dropped), and an answer over 128 KB is not kept; asking about such a call raises the timeout error as before (an idempotent call is then repeated). A window that is reloaded between a call and its question forgets the call, which is then sent again. A call that times out while still running leaves it running in Obsidian, as before. Recovery needs a `timeout` longer than `reply_grace`.
- **`eval` envelope**: `ObsidianCLI.eval(body, payload)` runs the body as an async function with the payload bound to `input`, and `run` returns the answer as one JSON line, `{ok: true, value}` or `{ok: false, error: {code, message}}`; an error message never carries the vault's absolute path. The `code` maps to `NoteNotFoundError`, `NoteExistsError`, `HeadingNotFoundError` or `InvalidArgumentError`; anything else is `ObsidianCLIError`. Output that does not start with `=> ` or is not JSON is an error, not data. Both call forms are a single expression, because `eval` evaluates a plain statement list as a script, where a top-level `return` is a syntax error.
- **Size ceiling**: the code travels as one argv entry, so the encoded payload is limited to about 900 KB (the call or the snippet around it adds at most a few tens of KB). Larger writes fail before spawning with `ContentTooLargeError`.

**CLI registration:** In Obsidian, open **Settings > General > Advanced**, turn **Command line interface** on, and accept the follow-up prompt to register it in your PATH. On Linux this copies Obsidian's bundled `obsidian-cli` to `~/.local/bin/obsidian` (mode 755); `~/.local/bin` must be on `PATH`. On Windows it appends the install directory to the user PATH; on macOS it links into `/usr/local/bin`. Verify with `obsidian version` (for example, `1.15.1 (installer 1.15.0)`).

**Vault resolution:** The CLI checks, in order: (1) the `vault=` argument sent by this server when `OBSIDIAN_VAULT` is set; (2) the calling process's CWD if it is inside a registered vault; (3) the most recently focused open vault window; and (4) otherwise fails with `Vault not found.`. Setting `OBSIDIAN_VAULT` to the vault's folder name is reliable, and Obsidian opens that vault's window on demand. A vault id from Obsidian's registry also works; see the README for the per-platform registry location.

### Vault (`vault.py`)

`Vault` holds no state and caches nothing: each method is one `eval` (or one CLI JSON command) and returns pydantic models. Paths are vault-relative with forward slashes and NFC-normalised, validated in Python before anything is sent (no absolute paths, `..`, backslashes, control characters or dot-folders).

| Method | Behaviour |
|--------|-----------|
| `list_files`, `read_note` | Recursive listing; text read of any non-binary file with Obsidian's parsed frontmatter, tags, links and headings |
| `write_note` | Create (folders included) or overwrite; never silently renames to `Note 1.md`; `.md` is appended unless the path's extension is a file type Obsidian opens (`md`, `canvas`, `base`, images, audio, video, `pdf`; case-insensitive), so `Learning Node.js` becomes `Learning Node.js.md` and `data.json` becomes `data.json.md`; content written verbatim |
| `append` | Atomic via `app.vault.process`; end of file, or end of a named section. A file that is not UTF-8 text is refused (`InvalidArgumentError`) before anything is written, so an attachment's bytes are never re-encoded |
| `append_unless_linked` | `add_link`'s write: one `editWithCache` step re-computes the note's links (links, embeds, frontmatter links, resolved like Obsidian does) and appends the bullet only if none points at the target, so concurrent calls add exactly one line and exactly one reports `added` |
| `replace_body` | `write_memory`'s update: one atomic edit that replaces the text after the frontmatter block and writes the given properties in place (the key's whole entry is replaced, or added at the end of the block; `defaults` only where the key is missing). Every other frontmatter line, the line endings and the BOM stay byte-identical; a note with no block gets one |
| `delete` | `app.fileManager.trashFile` unless `permanent` (then `app.vault.delete`); where the file goes follows Obsidian's "Deleted files" setting |
| `update_tags` | Adds and removes tags in one atomic edit of the frontmatter text: only the `tags` entry is rewritten, as a block list; every other line and the body stay byte-identical. Returns the resulting, added and removed tags; no write when nothing changes. A `---` block at the top that Obsidian does not read as properties (invalid YAML, a duplicate key, not a mapping) is refused with `InvalidArgumentError`, never shadowed by a new block; an empty or comment-only block gets the entry inside it. `replace_body` follows the same rule |
| `outgoing_links`, `backlinks`, `resolve_link`, `link_text` | From `metadataCache` (the cached links, embeds and frontmatter links of each file, resolved with `getFirstLinkpathDest`; `fileToLinktext`) |
| `tags`, `notes_with_tag` | Obsidian's own tag index, inline and frontmatter, counting occurrences the way the tag pane does |
| `search` | `search:context format=json`, de-duplicated per line; each matching line is capped at 300 characters around the match (`…` marks the cut) |
| `daily_path`, `read_daily`, `append_daily` | Daily notes core plugin options and template, for any date; `append_daily` also creates a missing heading section in the same edit; the plugin must be enabled (the Periodic Notes community plugin is not read) |
| `snapshot(folder="")` | Every note's path, size, modified time, frontmatter, tags, links and headings, plus the folders, in one eval. Used by onboarding, the knowledge base, stats and memory listing |

### Errors (`exceptions.py`)

`ObsidianError` subclasses `ToolError`, so any domain error raised inside a tool arrives as `is_error=True` with its message and needs no per-tool `try/except`. Subclasses: `CLINotFoundError`, `ObsidianNotRunningError`, `CLITimeoutError`, `ObsidianCLIError`, `NoteNotFoundError`, `NoteExistsError`, `HeadingNotFoundError`, `InvalidArgumentError`, `ContentTooLargeError`. No tool returns a success-shaped error body.

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OBSIDIAN_CLI_PATH` | No | auto-detected | Executable path when the CLI is not on `PATH`; set it to point at the binary explicitly |
| `OBSIDIAN_VAULT` | No | see vault resolution above | Vault folder name or id (not a filesystem path), passed as the CLI's `vault=` argument |

The Obsidian desktop app must be running with **Command line interface** enabled. `OBSIDIAN_VAULT` and `OBSIDIAN_CLI_PATH` are read when the server starts.

---

## MCP Server

The server uses `MCPServer` from the official `mcp` Python SDK, version 2.3 (`mcp>=2.3,<3`). Each module in `tools/` and `resources.py` exposes `register(server)`. Tools and resources reach the one stateless `Vault` through `get_vault()`.

Every tool returns a pydantic model (so clients get `structuredContent` and an output schema), carries `ToolAnnotations` (`readOnlyHint` / `destructiveHint` / `idempotentHint`, `openWorldHint=False`), describes each parameter with `Field(description=...)` and constraints (`Literal` enums, `ge`/`le`, patterns), and has a docstring that names its sibling tools and gives one example call. Server instructions are at most 20 lines: prerequisites, path conventions and "start with `get_vault_config`".

Run a local checkout through the package module:

```bash
uv run python -m obsidian_brain.server
```

### Tools (20)

| Area | Tool | Notes |
|------|------|-------|
| Notes | `list_vault_files(folder, extension, limit, offset)` | Paginated, returns `total` and `next_offset` |
| | `get_note(path)` | Exact text, frontmatter, tags, links, headings |
| | `write_note(path, content, overwrite=false)` | Create or replace; nothing is injected into the content |
| | `append_to_note(path, content, heading=None)` | End of file or end of the named section |
| | `delete_note(path, permanent=false)` | Trash by default |
| Tags | `update_tags(path, add, remove)` | Rewrites only the `tags` entry, as a block list; every other frontmatter line stays byte-identical; atomic |
| | `list_all_tags(limit)`, `get_notes_by_tag(tag, include_nested)` | Inline and frontmatter tags; `list_all_tags` counts occurrences like Obsidian |
| Links | `get_links(path, direction, depth)` | Backlinks and outgoing links, 1-3 hops |
| | `add_link(path, target, heading=None)` | Target resolved like a wikilink; idempotent |
| Search | `search_content(query, folder, limit)` | Obsidian's search syntax; `truncated` flag |
| Daily | `get_daily_note(date=None)` | Read-only; `exists` flag |
| | `append_to_daily(content, date, heading, timestamp, tags, links)` | Creates the note from the template for any date |
| Memory | `list_memories()` | One eval |
| | `read_memory(name)`, `write_memory(name, content, memory_type=None)`, `delete_memory(name)` | See "Memories" |
| Onboarding | `get_vault_config()` | Onboarding state, configuration, knowledge base status |
| | `run_onboarding(force=false)` | Never overwrites existing files unless `force` |
| Knowledge | `build_knowledge_base(include_orphans, include_link_patterns)` | Writes `Obsidian Brain/knowledge-base.md` |

### Resources

| Resource | MIME type | Description |
|----------|-----------|-------------|
| `vault://files` | `application/json` | Every file: `path`, `extension`, `size`, `modified`; Markdown entries also have a `vault://note/...` URI |
| `vault://note/{+path}` | `text/markdown` | Exact text of one note. `{+path}` is RFC 6570 reserved expansion, so `vault://note/Projects/Plan.md` works as well as `vault://note/Projects%2FPlan.md` |
| `vault://tags` | `application/json` | Every tag with its occurrence count (as `list_all_tags`) |
| `vault://stats` | `application/json` | `total_notes`, `total_folders` (all depths), `total_tags`, `total_links`, `orphan_notes`; `Obsidian Brain/` is not counted |
| `vault://knowledge` | `text/markdown` | The generated knowledge base |

Resources read the vault on every request. A failure is a protocol error (`ResourceNotFoundError` for a missing note or knowledge base, `ResourceError` for anything else), never a body that looks like data. IDE `@` pickers are host features, so the server cannot force resources into or customise them.

---

## Memories, Onboarding and Knowledge Base

All three write into a visible `Obsidian Brain/` folder (Obsidian does not index dot-folders). The `eval` transport has no extension restriction, but the vault profile stays a fenced YAML block inside a Markdown note so Obsidian renders it.

### Memories

A memory is a Markdown note in `Obsidian Brain/memories/`. One function decides which file a name means, and `list_memories`, `read_memory`, `write_memory` and `delete_memory` all use it.

- **Slug**: NFC-normalised, case-folded, every run of characters that are not letters, digits or combining marks becomes one `-`. `Project X`, `project_x` and `PROJECT-X.md` are the same slug; `A/B` and `AB` are not. A name with no letters or digits (`..`, `!!!`, `💥`) is rejected before anything is written, as is a slug over 200 bytes.
- **Name**: a memory's name is its `name` property, or its path inside the folder when it has none (so notes made by hand in Obsidian are listed, read and deleted under the name `list_memories` shows). Files whose names share a slug make the name ambiguous: every operation refuses and lists the paths.
- **Collisions**: `write_memory` creates `<slug>.md` with `name`, optional `type`, `created` and `updated`. Writing a memory whose slug belongs to a memory under a different spelling fails instead of overwriting; a file already at the target path is never overwritten by a create.
- **Updates**: `write_memory` replaces the body, keeps `created` and every other property (tags, custom keys), sets `updated`, and applies `memory_type` when given. It is one `replace_body` edit inside Obsidian: only the `type`, `updated` lines (and `name` and `created` when missing) are written, in place; every other frontmatter line, comments, `01234` and `1.10` included, stays byte-identical, and a concurrent `update_tags` or `write_memory` on the same memory loses nothing (the last body written wins). The properties' values come from Obsidian's metadata cache and the block is located by its reported position, never by splitting the file on `---`, so a `---` inside a value is harmless. Frontmatter Obsidian cannot parse is not rewritten: the call fails and says so.
- **Reads**: `read_memory` returns the body without the frontmatter block, `type`, `created`, `updated`, all frontmatter, and every tag (frontmatter and inline).
- **Delete**: moves the file to Obsidian's trash.

### Onboarding

`run_onboarding` takes one `snapshot()`, analyses it and writes three files: `Obsidian Brain/config.md` (fenced YAML profile), `memories/vault-overview.md` and `memories/conventions.md`.

- Files that already exist are **kept**, so edits survive a re-run; `force=true` regenerates and overwrites. The result lists `created`, `overwritten` and `kept`.
- Everything under `Obsidian Brain/` is excluded from the analysis, so a re-run sees the vault the first run saw.
- **Folder systems** are read from top-level folder names with numbering, emoji and case ignored (`1- Projects`, `2 - Areas`, `7 - Archives` are PARA): PARA (projects, areas, resources, archive/archives), Zettelkasten (two of permanent, literature, fleeting, inbox), Johnny.Decimal (`10-19 ...`) and ACE. Folder purposes (daily, templates, attachments, assets, inbox, maps of content) are reported under the real folder path. Depth is the deepest nesting level.
- **Templates**: a folder named `templates`/`template` (not a path substring), with its note count.
- **Tags** use Obsidian's tag list (frontmatter and inline); **frontmatter keys** count a key when 10% of notes use it; **naming** ignores date- and ID-named notes when judging prefixes and case. Every list is sorted, so output does not depend on file order. The generated memories show tags as code spans (`` `#tag` ``): bare `#tag` text in a note is a real tag in Obsidian's index and would inflate `list_all_tags`, `get_notes_by_tag` and `vault://tags`.
- `get_vault_config` returns `onboarded`, `partial` (the folder exists without `config.md`), the YAML from the first fenced block (text before or after the fence is fine; an unfenced file is returned whole), the memory count, the knowledge base status and a recommendation.

### Knowledge base

`build_knowledge_base` renders `Obsidian Brain/knowledge-base.md` from one `snapshot()`: overview table, folder tree, tag taxonomy, hub notes, optionally link patterns and orphans.

- Counts leave out `Obsidian Brain/`, so its own files are never notes, orphans or links. Folders are counted at every depth. Links are distinct note-to-note links (self-links and links to non-notes ignored); an orphan has none in or out.
- Timestamps are real UTC (`2026-11-23T03:24:12Z`). `created` is carried over from the previous version, `updated` is the current run.
- Table cells escape `|` and newlines. Tags are code spans, for the same reason as in onboarding.

---

## Error Handling

Application-level failures from the CLI arrive as a single stdout line with exit code 0 (`Vault not found.`, the CLI-disabled notice, `Error: ...`) and are classified by whole-line match, never by substring. The CLI failing to reach Obsidian exits 1 and writes `The CLI is unable to find Obsidian...` to stderr. Inside `eval`, a thrown JavaScript error is caught by the envelope and returned as `{ok: false, error}`, so it is never mistaken for output. A timeout is retried once for idempotent calls only (see Transport); the error for a timed-out write says it may have happened.

---

## Security Considerations

1. **No shell injection**: subprocesses use list-form argv, never `shell=True`.
2. **Payload as data**: tool arguments reach JavaScript only as one JSON literal; they are never spliced into code.
3. **Path validation**: absolute paths, `..`, backslashes, drive letters, control characters and dot-folders are rejected before any call.
4. **Explicit timeouts**: every CLI call is bounded and killed on expiry or cancellation.
5. **Errors never echo content**: messages never contain note text, the `eval` code or its payload, and carry at most 500 characters of CLI output. They do name the path, heading, link or tag involved.
6. **Trust boundary**: `eval` runs inside Obsidian with full plugin-API access. This server only sends the fixed snippets in `vault.py`; it never evaluates caller-supplied code.
7. **No secrets**: no API keys; the CLI talks to the local Obsidian instance.

---

## Testing

- `uv run pytest` runs the unit suite with no Obsidian: transport tests against a fake CLI script, tools and resources through an in-memory MCP client against fake vaults, and pure tests for slugs, onboarding heuristics and knowledge base rendering.
- `uv run pytest -m obsidian` runs live tests against the real CLI and a disposable vault named by `OBSIDIAN_TEST_VAULT` (the name must contain `testvault`). Each test works in its own folder or clears `Obsidian Brain/` before and after.
- The live concurrency tests (concurrent appends, tag edits, creates) use a client with a wide `max_evals`, so Obsidian itself sees overlapping edits; `TestEvalLoad` checks that a client with the default bound leaves no console replacement behind. Every overlap that ends out of order leaves one in the test vault's window (see Transport), so a window that has run many sessions is worth closing: `obsidian vault=<name> eval code="window.close()"`, and the next CLI call reopens it with a fresh heap.
- The unit tests drive the lost-reply protocol against a fake CLI that also plays the window (it keeps the log of request ids and answers questions about them, so a reply can be lost after the call ran, or the call lost before it arrived). The live `TestLostReply` does the same against the real window through a stand-in CLI that drops replies on purpose (the call ran and the reply is thrown away, the call never arrives, or it arrives 2 s late) and counts in the window how often each call ran.

---

## Upgrading from 0.1

0.2.0 requires `mcp>=2.3` and reduces the 29 tools of 0.1 to 20, with no aliases for the removed names.

| 0.1 tool | 0.2 replacement |
|----------|-----------------|
| `create_note`, `update_note` | `write_note` (`overwrite=true` to replace); no frontmatter, H1 or tags are injected |
| `add_tags`, `remove_tags` | `update_tags` |
| `get_backlinks`, `get_outgoing_links`, `get_linked_notes` | `get_links(direction, depth)` |
| `add_backlink` | `add_link` |
| `create_daily_entry` | `append_to_daily(timestamp=true, tags, links)` |
| `edit_memory` | `write_memory` |
| `check_onboarding_status`, `get_knowledge_base_status` | `get_vault_config` |
| `create_vault_knowledge_base` | `build_knowledge_base` |
| `refresh_vault_structure` | removed: nothing is cached |

`delete_note` trashes by default. The `vault://structure` resource is removed.

---

## Dependencies

```toml
requires-python = ">=3.12"
dependencies = [
    "mcp>=2.3,<3",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
]
```

No HTTP client libraries. No Docker deployment. Frontmatter is read from Obsidian's metadata cache; PyYAML only writes the YAML blocks for memories, the config and the knowledge base.
