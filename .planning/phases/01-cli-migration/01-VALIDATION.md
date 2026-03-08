---
phase: 1
slug: cli-migration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-08
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
| 1-01-01 | 01 | 1 | SDK-01 | unit | `pytest tests/test_server.py::test_server_init -x` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | SDK-02 | unit | `pytest tests/test_server.py::test_tool_registration -x` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | SDK-03 | unit | `pytest tests/test_server.py::test_resource_registration -x` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | SDK-04 | integration | `pytest tests/test_server.py::test_stdio_transport -x` | ❌ W0 | ⬜ pending |
| 1-01-05 | 01 | 1 | SDK-05 | unit | `pytest tests/test_dependencies.py::test_no_old_deps -x` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | CLI-01 | unit | `pytest tests/test_protocol.py -x` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 1 | CLI-02 | unit (mocked) | `pytest tests/test_cli_client.py -x` | ❌ W0 | ⬜ pending |
| 1-02-03 | 02 | 1 | CLI-03 | unit (mocked) | `pytest tests/test_cli_client.py::test_async_subprocess -x` | ❌ W0 | ⬜ pending |
| 1-02-04 | 02 | 1 | CLI-04 | unit | `pytest tests/test_parsers.py -x` | ❌ W0 | ⬜ pending |
| 1-02-05 | 02 | 1 | CLI-05 | unit (mocked) | `pytest tests/test_cli_client.py::test_timeout -x` | ❌ W0 | ⬜ pending |
| 1-02-06 | 02 | 1 | CLI-06 | unit | `pytest tests/test_cli_client.py::test_path_sanitization -x` | ❌ W0 | ⬜ pending |
| 1-02-07 | 02 | 1 | CLI-08 | unit | `pytest tests/test_cli_client.py::test_binary_detection -x` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 2 | TOOL-01 | integration (mocked) | `pytest tests/test_tools/ -x` | ❌ W0 | ⬜ pending |
| 1-03-02 | 03 | 2 | TOOL-02 | unit (mocked) | `pytest tests/test_cache_cli.py -x` | ❌ W0 | ⬜ pending |
| 1-03-03 | 03 | 2 | TOOL-04 | unit | `pytest tests/test_response_shapes.py -x` | ❌ W0 | ⬜ pending |
| 1-03-04 | 03 | 2 | TOOL-05 | snapshot | `pytest tests/test_snapshots.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_server.py` — FastMCP server init, tool/resource registration
- [ ] `tests/test_cli_client.py` — CLI client with mocked subprocess
- [ ] `tests/test_protocol.py` — VaultClient Protocol conformance
- [ ] `tests/test_parsers.py` — CLI JSON output parsing
- [ ] `tests/test_tools/` — Tool modules with mocked client
- [ ] `tests/test_response_shapes.py` — Response format backward compatibility
- [ ] `tests/conftest.py` — Shared fixtures (mock client, sample CLI outputs)
- [ ] Framework install: already configured in pyproject.toml; remove `pytest-httpx`, add `pytest-timeout`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CLI binary detection with real Obsidian | CLI-08 | Requires actual Obsidian install | 1. Install Obsidian 2. Run `obsidian --version` 3. Start server, verify no binary error |
| Backend switching via env var | CLI-07 | End-to-end with real vault | 1. Set `OBSIDIAN_BACKEND=cli` 2. Run tool 3. Set `OBSIDIAN_BACKEND=rest` 4. Run same tool 5. Compare output |
| 500-note cache refresh performance | TOOL-03 | Requires real 500-note vault | 1. Point at test vault 2. Time cache refresh 3. Verify < 10x REST baseline |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
