---
status: awaiting_human_verify
trigger: "The Obsidian Brain MCP server tools keep timing out when called from Claude Code"
created: 2026-03-08T00:00:00Z
updated: 2026-03-08T12:05:00Z
---

## Current Focus

hypothesis: CONFIRMED - root cause found and fix applied
test: All 197 tests pass, integration test returns 783 files and 641 tags
expecting: User confirms MCP tools work from Claude Code
next_action: Await human verification

## Symptoms

expected: MCP tools should return vault data from "/home/noahr/Nextcloud/Noah Work laptop/"
actual: CLI command times out after 30s, then MCP connection closes
errors: CLI command failed (exit -1): /usr/bin/obsidian files ext=md format=json -- Command timed out after 30.0s
reproduction: Call any mcp__obsidian-brain__ tool from Claude Code
started: Currently happening. User reports CLI works fine from their own terminal.

## Eliminated

- hypothesis: Wrong binary found (obsidian-cli vs obsidian)
  evidence: obsidian-cli is a third-party Go tool with different commands. The code correctly targets /usr/bin/obsidian which IS the Obsidian 1.12 CLI.
  timestamp: 2026-03-08T12:01:00Z

- hypothesis: Environment differences (DISPLAY, Wayland) blocking subprocess
  evidence: When Obsidian is running, subprocess calls from Python asyncio work perfectly. Environment vars are fine.
  timestamp: 2026-03-08T12:02:00Z

- hypothesis: JSON parsing issue with files command
  evidence: The files command returns plain text, not JSON. This is a secondary bug (would cause json.loads crash) but not the timeout cause.
  timestamp: 2026-03-08T12:02:30Z

## Evidence

- timestamp: 2026-03-08T12:00:00Z
  checked: /usr/bin/obsidian binary
  found: Shell script running `exec electron39 /usr/lib/obsidian/app.asar`. The Obsidian 1.12 CLI is built into the Electron app.
  implication: CLI commands are processed by the running Obsidian instance via IPC single-instance mechanism

- timestamp: 2026-03-08T12:01:00Z
  checked: Running `obsidian files ext=md format=json` with NO Obsidian running
  found: Command outputs startup logs then HANGS indefinitely. Exit code 124 (timeout).
  implication: ROOT CAUSE - CLI requires Obsidian desktop app to already be running

- timestamp: 2026-03-08T12:02:00Z
  checked: Started Obsidian, then ran same command
  found: Returns 49KB of file paths in <10s. Works perfectly via asyncio subprocess.
  implication: Confirms hypothesis - running app is the prerequisite

- timestamp: 2026-03-08T12:02:30Z
  checked: Output format of `files ext=md format=json`
  found: Returns plain text (one path per line), NOT JSON. `tags format=json` does return JSON.
  implication: Secondary bug - get_all_files/list_directory used _run_json but should use _run

- timestamp: 2026-03-08T12:04:00Z
  checked: Integration test after fix
  found: 783 files and 641 tags returned successfully through fixed client
  implication: Fix works correctly with running Obsidian

- timestamp: 2026-03-08T12:05:00Z
  checked: Full test suite
  found: 197/197 tests pass
  implication: No regressions from changes

## Resolution

root_cause: The Obsidian 1.12 CLI works via IPC -- the `obsidian` binary detects a running Obsidian instance and sends commands to it. If NO Obsidian instance is running, the binary launches a full Electron/GUI app that hangs waiting for user interaction, causing the 30s timeout. Additionally, the `files` command returns plain text (not JSON), so `_run_json` would crash with json.loads even if the timeout didn't hit first.
fix: 1. Added pre-flight `_check_obsidian_running()` that uses pgrep to verify Obsidian is running before any CLI call, raising `ObsidianNotRunningError` with clear instructions. 2. Added `_filter_log_lines()` to strip Obsidian Electron startup log lines from stdout. 3. Fixed `get_all_files()` and `list_directory()` to use `_run()` (plain text) instead of `_run_json()`. 4. Added `ObsidianNotRunningError` exception with user-friendly message.
verification: 197/197 tests pass. Integration test with running Obsidian returns 783 files and 641 tags.
files_changed:
  - src/obsidian_brain/exceptions.py
  - src/obsidian_brain/cli_client.py
  - tests/test_cli_client.py
