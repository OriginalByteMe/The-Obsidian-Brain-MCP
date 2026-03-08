# Technology Stack

**Analysis Date:** 2026-03-08

## Languages

**Primary:**
- Python 3.12+ - All application code (`src/obsidian_brain/`)

**Secondary:**
- YAML - Configuration files (`pyproject.toml`, `docker-compose.yml`, vault config generation)
- Markdown - Memory/knowledge base content generation

## Runtime

**Environment:**
- Python 3.12 (minimum, specified in `pyproject.toml` `requires-python = ">=3.12"`)
- Docker via `python:3.12-slim` base image (`Dockerfile`)

**Package Manager:**
- uv - Primary package manager (used in `Dockerfile` and development)
- Lockfile: `uv.lock` present

## Frameworks

**Core:**
- mcp-use >= 1.5.1 - MCP (Model Context Protocol) server framework. Provides `MCPServer` class with `@server.tool()` and `@server.resource()` decorators for registering tools and resources. Server runs via stdio transport.
- httpx >= 0.27.0 - Async HTTP client for communicating with Obsidian Local REST API
- pydantic >= 2.0.0 - Data modeling and validation (`src/obsidian_brain/models.py`)
- python-frontmatter >= 1.1.0 - YAML frontmatter parsing/manipulation for Obsidian notes (`src/obsidian_brain/utils/frontmatter.py`)

**Testing:**
- pytest >= 8.0.0 - Test runner (dev dependency)
- pytest-asyncio >= 0.23.0 - Async test support with `asyncio_mode = "auto"` (`pyproject.toml`)
- pytest-httpx >= 0.30.0 - HTTP mocking for httpx client tests (dev dependency)

**Build/Dev:**
- hatchling - Build backend (`pyproject.toml` `[build-system]`)
- ruff >= 0.4.0 - Linting and formatting (dev dependency)
- mypy >= 1.10.0 - Static type checking with `strict = true` (dev dependency)

## Key Dependencies

**Critical:**
- `mcp-use` >= 1.5.1 - Core MCP server framework; the entire application is built around `MCPServer` from this package. Used in `src/obsidian_brain/server.py` and all tool/resource registration modules.
- `httpx` >= 0.27.0 - All Obsidian API communication flows through `httpx.AsyncClient` in `src/obsidian_brain/client.py`. Uses async context manager pattern with 30-second timeout.
- `pydantic` >= 2.0.0 - All data models (`VaultStructure`, `NoteMetadata`, `FolderNode`, `LinkGraph`, etc.) in `src/obsidian_brain/models.py`.

**Infrastructure:**
- `python-frontmatter` >= 1.1.0 - Parses and manipulates YAML frontmatter in Obsidian notes. Used throughout `src/obsidian_brain/utils/frontmatter.py`.
- `pyyaml` (transitive via python-frontmatter and direct import) - YAML serialization in `src/obsidian_brain/memory.py` and `src/obsidian_brain/onboarding.py`.

## Configuration

**Environment:**
- `.env` file present (secrets - not read)
- `.env.example` documents all env vars
- Required: `OBSIDIAN_API_KEY` - Bearer token for Obsidian Local REST API authentication
- Optional: `OBSIDIAN_URL` - Full base URL override (overrides host/port)
- Optional: `OBSIDIAN_HOST` - API host (default: `127.0.0.1`)
- Optional: `OBSIDIAN_PORT` - API port (default: `27124`)
- Optional: `OBSIDIAN_VERIFY_SSL` - SSL verification (default: `false`, self-signed cert)
- Environment vars read directly in `src/obsidian_brain/client.py` via `os.getenv()`

**Build:**
- `pyproject.toml` - Project metadata, dependencies, tool configuration (ruff, pytest, mypy)
- `Dockerfile` - Production container build
- `docker-compose.yml` - Container orchestration with env var passthrough

**Linting/Formatting:**
- Ruff configured in `pyproject.toml`:
  - `line-length = 100`
  - `target-version = "py312"`
  - Rules: E, F, I (isort), UP (pyupgrade), B (bugbear), SIM (simplify)
  - Ignored: E501 (line length handled separately)

**Type Checking:**
- mypy configured in `pyproject.toml`:
  - `python_version = "3.12"`
  - `strict = true`

## Platform Requirements

**Development:**
- Python 3.12+
- uv package manager
- Access to Obsidian instance with Local REST API plugin enabled
- Obsidian Local REST API plugin installed and configured with API key

**Production:**
- Docker (via `python:3.12-slim`)
- Network access to Obsidian host (uses `host.docker.internal` in Docker for Mac/Windows)
- stdio transport for MCP communication (stdin/stdout)

**Entry Points:**
- CLI: `obsidian-brain` command (maps to `obsidian_brain.server:main`)
- Module: `python -m obsidian_brain.server`
- Docker: `uv run python -m obsidian_brain.server`

---

*Stack analysis: 2026-03-08*
