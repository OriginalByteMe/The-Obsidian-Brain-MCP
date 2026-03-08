# Codebase Structure

**Analysis Date:** 2026-03-08

## Directory Layout

```
The-Obsidian-Brain-MCP/
├── src/
│   └── obsidian_brain/          # Main Python package
│       ├── __init__.py           # Package init, __version__
│       ├── server.py             # MCP server setup and entry point
│       ├── client.py             # Obsidian REST API async client
│       ├── cache.py              # In-memory vault structure cache
│       ├── models.py             # Pydantic data models
│       ├── knowledge.py          # Knowledge base generator
│       ├── memory.py             # Memory manager
│       ├── onboarding.py         # Vault onboarding/analysis
│       ├── tools/                # MCP tool definitions (8 modules)
│       │   ├── __init__.py
│       │   ├── vault.py          # CRUD operations on notes
│       │   ├── links.py          # Wikilink/backlink management
│       │   ├── tags.py           # Tag management
│       │   ├── search.py         # Full-text and DQL search
│       │   ├── daily.py          # Daily/periodic note tools
│       │   ├── knowledge.py      # Knowledge base tools
│       │   ├── onboarding.py     # Onboarding tools
│       │   └── memory.py         # Memory CRUD tools
│       ├── resources/            # MCP resource definitions
│       │   ├── __init__.py
│       │   ├── structure.py      # vault://structure, vault://tags, vault://stats
│       │   └── knowledge.py      # vault://knowledge
│       └── utils/                # Shared utilities
│           ├── __init__.py       # Re-exports key functions
│           ├── frontmatter.py    # YAML frontmatter parsing/manipulation
│           └── wikilinks.py      # [[wikilink]] extraction/injection
├── tests/                        # Test directory (currently empty)
│   └── __init__.py
├── scripts/                      # Utility scripts (currently empty)
├── assets/                       # README images and demo GIFs
├── .serena/                      # Serena AI configuration
├── main.py                       # Dev/example server (NOT production entry)
├── pyproject.toml                # Project metadata, dependencies, tool config
├── uv.lock                       # Locked dependencies
├── Dockerfile                    # Container build
├── docker-compose.yml            # Container orchestration
├── .env.example                  # Environment variable template
├── .env                          # Local environment (gitignored)
├── .python-version               # Python version pin
├── .mcp.json                     # MCP client configuration
├── SPECIFICATION.md              # Detailed project specification
├── README.md                     # Project documentation
└── LICENSE                       # MIT license
```

## Directory Purposes

**`src/obsidian_brain/`:**
- Purpose: Main application package containing all server logic
- Contains: Server entry point, API client, cache, models, domain managers
- Key files: `server.py` (entry point), `client.py` (API wrapper), `cache.py` (state), `models.py` (types)

**`src/obsidian_brain/tools/`:**
- Purpose: MCP tool definitions organized by domain
- Contains: 8 Python modules, each exporting a `register_*_tools(server)` function
- Key files: `vault.py` (core CRUD), `links.py` (link graph), `memory.py` (persistence)

**`src/obsidian_brain/resources/`:**
- Purpose: MCP resource definitions (read-only data endpoints)
- Contains: 2 modules exposing 4 URI-based resources
- Key files: `structure.py` (3 resources), `knowledge.py` (1 resource)

**`src/obsidian_brain/utils/`:**
- Purpose: Shared text manipulation utilities for Obsidian-specific formats
- Contains: Frontmatter and wikilink parsing/manipulation
- Key files: `frontmatter.py` (9 functions), `wikilinks.py` (6 functions)

**`tests/`:**
- Purpose: Test directory (placeholder, no tests written yet)
- Contains: Only `__init__.py`

**`scripts/`:**
- Purpose: Utility scripts (currently empty, only `__pycache__`)

**`assets/`:**
- Purpose: Static assets for README (logo, demo GIF)

## Key File Locations

**Entry Points:**
- `src/obsidian_brain/server.py`: Production MCP server entry point (stdio transport)
- `main.py`: Development server with streamable-http transport and debug mode

**Configuration:**
- `pyproject.toml`: Project metadata, dependencies, ruff/pytest/mypy config
- `.env.example`: Environment variable template (API key, host, port)
- `docker-compose.yml`: Container configuration with env var passthrough
- `.mcp.json`: MCP client configuration for connecting to this server

**Core Logic:**
- `src/obsidian_brain/client.py`: All HTTP communication with Obsidian REST API
- `src/obsidian_brain/cache.py`: Vault structure caching and backlink indexing
- `src/obsidian_brain/onboarding.py`: Vault pattern detection (PARA, Zettelkasten, etc.)
- `src/obsidian_brain/knowledge.py`: Knowledge base markdown generation
- `src/obsidian_brain/memory.py`: Memory file management

**Models:**
- `src/obsidian_brain/models.py`: All Pydantic models (9 total)

**Testing:**
- `tests/`: Empty test directory (configured in `pyproject.toml` with `asyncio_mode = "auto"`)

## Naming Conventions

**Files:**
- snake_case for all Python files: `vault.py`, `frontmatter.py`, `wikilinks.py`
- Matching domain names between tools and managers: `tools/knowledge.py` uses `knowledge.py`, `tools/memory.py` uses `memory.py`

**Directories:**
- Lowercase, no separators: `tools/`, `resources/`, `utils/`
- Package uses underscore: `obsidian_brain/`

**Modules:**
- Tool modules named by domain: `vault`, `links`, `tags`, `search`, `daily`, `knowledge`, `onboarding`, `memory`
- Resource modules named by what they expose: `structure`, `knowledge`
- Utility modules named by what they manipulate: `frontmatter`, `wikilinks`

## Where to Add New Code

**New MCP Tool:**
1. Create `src/obsidian_brain/tools/{domain}.py`
2. Define `register_{domain}_tools(server: MCPServer) -> None`
3. Inside, define async functions decorated with `@server.tool()`
4. Import and call the registration function in `src/obsidian_brain/server.py`
5. Follow the pattern: create `ObsidianClient()` context manager per tool call, return JSON strings

**New MCP Resource:**
1. Create `src/obsidian_brain/resources/{name}.py`
2. Define `register_{name}_resource(server: MCPServer) -> None`
3. Inside, define functions decorated with `@server.resource(uri="vault://{name}", mime_type="...")`
4. Import and call in `src/obsidian_brain/server.py`

**New Domain Manager:**
1. Create `src/obsidian_brain/{domain}.py`
2. Define a manager class with business logic methods
3. Export a module-level singleton instance: `{domain}_manager = {Domain}Manager()`
4. Import the singleton in the corresponding tool module

**New Pydantic Model:**
- Add to `src/obsidian_brain/models.py`

**New Utility Function:**
- Add to the appropriate file in `src/obsidian_brain/utils/`
- If creating a new utility module, add re-exports to `src/obsidian_brain/utils/__init__.py`

**New Tests:**
- Place in `tests/` directory
- Name files `test_{module}.py`
- Use `pytest-asyncio` for async tests (auto mode configured)
- Use `pytest-httpx` for mocking HTTP calls

## Special Directories

**`.serena/`:**
- Purpose: Serena AI tool configuration
- Generated: Yes (by Serena)
- Committed: Yes

**`.venv/`:**
- Purpose: Python virtual environment (Python 3.14)
- Generated: Yes (by `uv`)
- Committed: No (in `.gitignore`)

**`Obsidian Brain/` (in vault, not in repo):**
- Purpose: Server creates this folder inside the user's Obsidian vault for config and memories
- Contains: `config.yml`, `memories/*.md`, `knowledge-base.md`
- Path constants defined in `src/obsidian_brain/onboarding.py`: `CONFIG_PATH`, `MEMORIES_PATH`

---

*Structure analysis: 2026-03-08*
