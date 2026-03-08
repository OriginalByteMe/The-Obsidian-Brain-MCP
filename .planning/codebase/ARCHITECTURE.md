# Architecture

**Analysis Date:** 2026-03-08

## Pattern Overview

**Overall:** MCP Server with Registration Pattern (tool/resource modules registered onto a central server instance)

**Key Characteristics:**
- Single-process MCP server communicating over stdio transport
- Async HTTP client wrapping the Obsidian Local REST API
- In-memory cache (singleton) for vault structure with on-demand refresh
- Tool functions registered via decorator pattern on `MCPServer` instance
- Global singleton managers for cross-cutting concerns (cache, knowledge, memory, onboarding)
- All vault interactions proxied through Obsidian's Local REST API (never direct filesystem access)

## Layers

**MCP Server (Entry Point):**
- Purpose: Initialize server, register all tools and resources, run transport
- Location: `src/obsidian_brain/server.py`
- Contains: Server instantiation, tool/resource registration calls, `main()` entry point
- Depends on: `mcp_use.server.MCPServer`, all tool and resource registration functions
- Used by: CLI entry point (`obsidian-brain` command), Docker CMD

**Tools (MCP Tool Handlers):**
- Purpose: Define MCP-callable tool functions that implement vault operations
- Location: `src/obsidian_brain/tools/`
- Contains: 8 tool modules, each with a `register_*_tools(server)` function
- Depends on: `ObsidianClient`, `vault_cache`, utility functions, Pydantic models
- Used by: MCP server (registered at startup, invoked by LLM clients)

**Resources (MCP Resource Handlers):**
- Purpose: Expose read-only vault data as MCP resources (URI-addressable)
- Location: `src/obsidian_brain/resources/`
- Contains: 2 resource modules exposing `vault://structure`, `vault://tags`, `vault://stats`, `vault://knowledge`
- Depends on: `vault_cache`, `ObsidianClient`, `knowledge` module
- Used by: MCP server (registered at startup, read by LLM clients)

**Client (API Wrapper):**
- Purpose: Async HTTP client wrapping all Obsidian Local REST API endpoints
- Location: `src/obsidian_brain/client.py`
- Contains: `ObsidianClient` class (async context manager), custom exceptions
- Depends on: `httpx`, environment variables for configuration
- Used by: All tool modules, resource modules, cache module

**Cache (In-Memory State):**
- Purpose: Cache vault structure (folders, notes, metadata, backlinks) to avoid repeated API calls
- Location: `src/obsidian_brain/cache.py`
- Contains: `VaultCache` class, global `vault_cache` singleton
- Depends on: `ObsidianClient` (for refresh), Pydantic models, wikilink utilities
- Used by: Tool modules (links, tags, vault, onboarding), resource modules

**Domain Managers (Business Logic):**
- Purpose: Encapsulate domain-specific logic separate from MCP tool definitions
- Location: `src/obsidian_brain/knowledge.py`, `src/obsidian_brain/memory.py`, `src/obsidian_brain/onboarding.py`
- Contains: `KnowledgeBaseManager`, `MemoryManager`, `OnboardingManager` (all singletons)
- Depends on: Pydantic models, YAML library
- Used by: Corresponding tool modules

**Models (Data Structures):**
- Purpose: Define typed data structures for vault representation
- Location: `src/obsidian_brain/models.py`
- Contains: 9 Pydantic models (`FolderNode`, `NoteMetadata`, `VaultStructure`, `NoteContent`, `SearchMatch`, `LinkGraph`, etc.)
- Depends on: `pydantic`
- Used by: Cache, tools, resources, knowledge manager

**Utilities (Shared Helpers):**
- Purpose: Low-level text manipulation for Obsidian-specific formats
- Location: `src/obsidian_brain/utils/`
- Contains: Frontmatter parsing/manipulation, wikilink extraction/injection/resolution
- Depends on: `python-frontmatter`, `re`
- Used by: Tool modules, cache module

## Data Flow

**Tool Invocation (typical):**

1. LLM client sends MCP tool call (e.g., `get_note`)
2. Tool function in `src/obsidian_brain/tools/vault.py` is invoked
3. Tool creates `ObsidianClient()` as async context manager
4. Client makes HTTP request to Obsidian Local REST API (localhost:27124)
5. Response is parsed, optionally enriched (e.g., wikilink extraction)
6. Result serialized as JSON string and returned to MCP client

**Cache-Dependent Operations (backlinks, tags, link graph):**

1. Tool checks `vault_cache.is_initialized`
2. If not initialized, returns error instructing user to call `refresh_vault_structure`
3. If initialized, queries in-memory cache directly (no API call)
4. Cache was populated by prior `refresh_vault_structure` call which:
   a. Recursively lists all vault files via API
   b. Fetches metadata for each `.md` file
   c. Extracts wikilinks from content
   d. Builds backlink index
   e. Computes aggregate statistics

**Onboarding Flow:**

1. `check_onboarding_status` - scans vault files for `Obsidian Brain/config.yml`
2. `refresh_vault_structure` - populates in-memory cache (prerequisite)
3. `run_onboarding` - analyzes cached structure, detects patterns (PARA, Zettelkasten, etc.)
4. Generates `config.yml`, `vault-overview.md`, `conventions.md` via Obsidian API

**State Management:**
- **In-memory cache:** `vault_cache` singleton in `src/obsidian_brain/cache.py` - stores `VaultStructure` with folders, notes, backlink index
- **Persistent state:** Stored as markdown files in the Obsidian vault under `Obsidian Brain/` folder (config, memories, knowledge base)
- **No database:** All persistence is via Obsidian's file system through the REST API
- **Cache invalidation:** Manual only - user must call `refresh_vault_structure`

## Key Abstractions

**ObsidianClient:**
- Purpose: Single point of contact with Obsidian Local REST API
- Examples: `src/obsidian_brain/client.py`
- Pattern: Async context manager (`async with ObsidianClient() as client`). Every tool creates its own client instance per invocation.

**VaultCache:**
- Purpose: Avoid repeated API calls for structure queries
- Examples: `src/obsidian_brain/cache.py`
- Pattern: Global singleton with explicit refresh. Lock-protected rebuild. Provides backlink index, tag queries, note metadata lookup.

**Registration Functions:**
- Purpose: Modular tool/resource registration without circular imports
- Examples: `register_vault_tools()`, `register_link_tools()`, `register_structure_resource()`
- Pattern: Each module exports a single `register_*` function that takes the server and decorates inner functions with `@server.tool()` or `@server.resource()`.

**Manager Singletons:**
- Purpose: Encapsulate business logic for specific domains
- Examples: `knowledge_manager` in `src/obsidian_brain/knowledge.py`, `memory_manager` in `src/obsidian_brain/memory.py`, `onboarding_manager` in `src/obsidian_brain/onboarding.py`
- Pattern: Module-level singleton instance of a manager class. Stateless (logic only, no stored data). Used by corresponding tool modules.

## Entry Points

**Primary - CLI:**
- Location: `src/obsidian_brain/server.py` (`main()` function)
- Triggers: `obsidian-brain` CLI command (defined in `pyproject.toml` `[project.scripts]`)
- Responsibilities: Creates MCPServer, registers all tools/resources, runs with stdio transport

**Development - main.py:**
- Location: `main.py` (project root)
- Triggers: `python main.py` for development
- Responsibilities: Example/dev server using `mcp_use` with streamable-http transport and debug mode. NOT the production entry point.

**Docker:**
- Location: `Dockerfile`
- Triggers: `docker compose up`
- Responsibilities: Runs `uv run python -m obsidian_brain.server` in container with stdio transport

## Error Handling

**Strategy:** Return JSON error objects from tools (never raise exceptions to MCP client)

**Patterns:**
- Custom exception hierarchy: `ObsidianAPIError` -> `NoteNotFoundError` in `src/obsidian_brain/client.py`
- `CacheNotInitializedError` in `src/obsidian_brain/cache.py` for uninitialized cache access
- Every tool function wraps operations in try/except and returns `{"error": True, "type": "...", "message": "..."}` JSON
- Client-level errors are caught and re-wrapped with context (status code, path)
- Silent failure: Cache refresh skips notes that fail to read (`except Exception: continue`)

## Cross-Cutting Concerns

**Logging:** No logging framework. No structured logging. Errors are returned as JSON to the caller.

**Validation:** Input validation within tool functions (empty strings, date formats, valid enum values). Pydantic models validate structure but are primarily used for serialization.

**Authentication:** Bearer token auth to Obsidian REST API. Token read from `OBSIDIAN_API_KEY` environment variable. Applied in `ObsidianClient._get_headers()`.

**Configuration:** Environment variables only (`OBSIDIAN_API_KEY`, `OBSIDIAN_HOST`, `OBSIDIAN_PORT`, `OBSIDIAN_URL`, `OBSIDIAN_VERIFY_SSL`). Read in `ObsidianClient.__init__()`. No config file for the server itself (vault config is separate).

---

*Architecture analysis: 2026-03-08*
