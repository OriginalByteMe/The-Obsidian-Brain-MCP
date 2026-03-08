# External Integrations

**Analysis Date:** 2026-03-08

## APIs & External Services

**Obsidian Local REST API:**
- The sole external API integration. All vault operations go through this REST API.
- SDK/Client: Custom async wrapper `ObsidianClient` in `src/obsidian_brain/client.py`
- Auth: Bearer token via `OBSIDIAN_API_KEY` env var
- Base URL: Constructed from `OBSIDIAN_HOST`:`OBSIDIAN_PORT` (default `https://127.0.0.1:27124`) or overridden via `OBSIDIAN_URL` env var
- SSL: Self-signed certificate, verification disabled by default (`OBSIDIAN_VERIFY_SSL=false`)
- Timeout: 30 seconds (`httpx.AsyncClient` timeout in `src/obsidian_brain/client.py` line 89)
- Transport: HTTPS with Bearer token in `Authorization` header

**API Endpoints Used (in `src/obsidian_brain/client.py`):**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Server info and auth status |
| `/vault/{path}` | GET | Read note content/metadata |
| `/vault/{path}` | PUT | Create or replace note |
| `/vault/{path}` | POST | Append to note |
| `/vault/{path}` | PATCH | Partial update (append/prepend/replace at target) |
| `/vault/{path}` | DELETE | Delete note |
| `/vault/{path}/` | GET | List directory contents |
| `/search/simple/` | POST | Full-text search |
| `/search/` | POST | DQL (Dataview) or JsonLogic queries |
| `/periodic/{period}/` | GET/POST/PUT | Read/append/replace periodic notes |
| `/periodic/{period}/{year}/{month}/{day}/` | GET/POST/PUT | Date-specific periodic notes |

**Custom Headers:**
- `Accept: application/vnd.olrapi.note+json` - Request JSON with metadata
- `Accept: text/markdown` - Request raw markdown
- `Content-Type: application/vnd.olrapi.dataview.dql+txt` - DQL query
- `Content-Type: application/vnd.olrapi.jsonlogic+json` - JsonLogic query
- `Operation` / `Target-Type` / `Target` - PATCH operation control headers

**MCP Protocol (Model Context Protocol):**
- Framework: `mcp-use` library
- Transport: stdio (stdin/stdout) for LLM client communication
- Server initialization: `src/obsidian_brain/server.py`
- Tools registered: 25+ tools across 8 tool modules
- Resources registered: `vault://structure`, `vault://tags`, `vault://stats`, `vault://knowledge`

## Data Storage

**Databases:**
- None. No traditional database is used.

**In-Memory Cache:**
- `VaultCache` singleton in `src/obsidian_brain/cache.py`
- Stores: folder hierarchy, note metadata (tags, links, frontmatter), backlink index, vault statistics
- Must be explicitly refreshed via `refresh_vault_structure` tool
- Protected by `asyncio.Lock` for concurrent access safety
- No persistence - rebuilt from Obsidian API on each server session

**File Storage:**
- All persistent data stored as files within the Obsidian vault itself via the REST API
- Configuration: `Obsidian Brain/config.yml` (in vault, defined in `src/obsidian_brain/onboarding.py`)
- Memories: `Obsidian Brain/memories/*.md` (in vault, defined in `src/obsidian_brain/onboarding.py`)
- Knowledge base: `.obsidian-brain/knowledge-base.md` (in vault, defined in `src/obsidian_brain/knowledge.py`)

**Caching:**
- In-memory only via `VaultCache` singleton (`vault_cache` in `src/obsidian_brain/cache.py`)
- No Redis, Memcached, or other external cache

## Authentication & Identity

**Auth Provider:**
- Obsidian Local REST API plugin generates API keys
- Implementation: Bearer token passed in `Authorization` header
- Token source: `OBSIDIAN_API_KEY` environment variable
- No user authentication/identity system - single-user tool

## Monitoring & Observability

**Error Tracking:**
- None. No external error tracking service (Sentry, etc.)

**Logs:**
- No structured logging framework
- Errors silently caught in several places (e.g., `src/obsidian_brain/cache.py` line 191 catches all exceptions during note metadata fetch)
- Custom exception hierarchy: `ObsidianAPIError` and `NoteNotFoundError` in `src/obsidian_brain/client.py`

## CI/CD & Deployment

**Hosting:**
- Self-hosted via Docker or direct Python execution
- Docker: `Dockerfile` + `docker-compose.yml` for containerized deployment
- Designed to run alongside Obsidian desktop app (connects to localhost API)

**CI Pipeline:**
- None detected. No `.github/workflows/`, no CI configuration files.

## Environment Configuration

**Required env vars:**
- `OBSIDIAN_API_KEY` - API key from Obsidian Local REST API plugin

**Optional env vars:**
- `OBSIDIAN_URL` - Full base URL override
- `OBSIDIAN_HOST` - API host (default: `127.0.0.1`)
- `OBSIDIAN_PORT` - API port (default: `27124`)
- `OBSIDIAN_VERIFY_SSL` - SSL cert verification (default: `false`)

**Secrets location:**
- `.env` file in project root (gitignored)
- `.env.example` provides template

## Webhooks & Callbacks

**Incoming:**
- None. The MCP server communicates via stdio, not HTTP webhooks.

**Outgoing:**
- None. The server only makes requests to the Obsidian Local REST API.

## Integration Architecture

```
LLM Client (e.g., Claude)
    |
    | stdio (MCP Protocol)
    |
    v
obsidian-brain MCP Server (src/obsidian_brain/server.py)
    |
    | HTTPS + Bearer Token
    |
    v
Obsidian Local REST API Plugin
    |
    | Direct file access
    |
    v
Obsidian Vault (filesystem)
```

The server acts as a bridge: it receives MCP tool calls via stdio from an LLM client, translates them to REST API calls against the Obsidian plugin, and returns structured results back through MCP.

---

*Integration audit: 2026-03-08*
