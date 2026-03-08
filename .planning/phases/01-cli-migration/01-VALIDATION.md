---
phase: 1
slug: cli-migration
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-08
updated: 2026-03-08
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.23.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/ -x --timeout=30` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x --timeout=30`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-00-01 | 00 | 0 | TOOL-05 | snapshot | `pytest tests/test_snapshots.py tests/test_response_shapes.py -x` | Plan 00 creates | pending |
| 1-01-01 | 01 | 1 | CLI-01 | unit | `pytest tests/test_protocol.py -x` | Plan 01 creates | pending |
| 1-01-02 | 01 | 1 | CLI-02 | unit (mocked) | `pytest tests/test_cli_client.py -x` | Plan 01 creates | pending |
| 1-01-03 | 01 | 1 | CLI-03 | unit (mocked) | `pytest tests/test_cli_client.py::test_async_subprocess -x` | Plan 01 creates | pending |
| 1-01-04 | 01 | 1 | CLI-04 | unit | `pytest tests/test_parsers.py -x` | Plan 01 creates | pending |
| 1-01-05 | 01 | 1 | CLI-05 | unit (mocked) | `pytest tests/test_cli_client.py::test_timeout -x` | Plan 01 creates | pending |
| 1-01-06 | 01 | 1 | CLI-06 | unit | `pytest tests/test_cli_client.py::test_path_sanitization -x` | Plan 01 creates | pending |
| 1-01-07 | 01 | 1 | CLI-08 | unit | `pytest tests/test_cli_client.py::test_binary_detection -x` | Plan 01 creates | pending |
| 1-02-01 | 02 | 2 | SDK-01 | unit | `pytest tests/test_server.py::test_server_init -x` | Plan 02 creates | pending |
| 1-02-02 | 02 | 2 | SDK-02 | unit | `pytest tests/test_server.py::test_tool_registration -x` | Plan 02 creates | pending |
| 1-02-03 | 02 | 2 | SDK-03 | unit | `pytest tests/test_server.py::test_resource_registration -x` | Plan 02 creates | pending |
| 1-02-04 | 02 | 2 | SDK-04 | integration | `pytest tests/test_server.py::test_stdio_transport -x` | Plan 02 creates | pending |
| 1-02-05 | 02 | 2 | TOOL-01 | integration (mocked) | `pytest tests/test_tools_core.py -x` | Plan 02 creates | pending |
| 1-02-06 | 02 | 2 | TOOL-04 | unit | `pytest tests/test_tools_core.py -x` | Plan 02 creates | pending |
| 1-03-01 | 03 | 2 | TOOL-01 | integration (mocked) | `pytest tests/test_tools_higher.py -x` | Plan 03 creates | pending |
| 1-03-02 | 03 | 2 | TOOL-04 | unit | `pytest tests/test_tools_higher.py -x` | Plan 03 creates | pending |
| 1-04-01 | 04 | 3 | TOOL-02 | unit (mocked) | `pytest tests/test_cache_cli.py -x` | Plan 04 creates | pending |
| 1-04-02 | 04 | 3 | SDK-05 | unit | `pytest tests/test_dependencies.py::test_no_old_deps -x` | Plan 04 creates | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_snapshots.py` — Pre-migration response shape snapshots (Plan 00)
- [ ] `tests/test_response_shapes.py` — Response format backward compatibility assertions (Plan 00)
- [ ] Framework install: already configured in pyproject.toml; remove `pytest-httpx`, add `pytest-timeout`

## Wave 1 Requirements

- [ ] `tests/test_protocol.py` — VaultClient Protocol conformance (Plan 01)
- [ ] `tests/test_cli_client.py` — CLI client with mocked subprocess (Plan 01)
- [ ] `tests/test_parsers.py` — CLI JSON output parsing (Plan 01)
- [ ] `tests/conftest.py` — Shared fixtures (mock client, sample CLI outputs) (Plan 01)

## Wave 2 Requirements

- [ ] `tests/test_server.py` — FastMCP server init, tool/resource registration (Plan 02)
- [ ] `tests/test_tools_core.py` — Core tool modules with mocked VaultClient (Plan 02)
- [ ] `tests/test_tools_higher.py` — Higher-level tool modules with mocked VaultClient (Plan 03)

## Wave 3 Requirements

- [ ] `tests/test_cache_cli.py` — Cache integration with mocked VaultClient (Plan 04)
- [ ] `tests/test_dependencies.py` — Dependency hygiene (Plan 04)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CLI binary detection with real Obsidian | CLI-08 | Requires actual Obsidian install | 1. Install Obsidian 2. Run `obsidian --version` 3. Start server, verify no binary error |
| 500-note cache refresh performance | TOOL-03 | Requires real 500-note vault | 1. Point at test vault 2. Time cache refresh 3. Verify < 10x REST baseline |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or wave dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
