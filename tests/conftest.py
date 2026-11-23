"""Shared fixtures: a live Obsidian test vault for `@pytest.mark.obsidian` tests.

Live tests run against the real Obsidian CLI and a disposable vault named by the
environment variable OBSIDIAN_TEST_VAULT (the name must contain "testvault"; anything
else is refused). Each test gets its own subfolder, deleted afterwards, inside one
per-session folder that is also deleted at the end. Run them with:

    OBSIDIAN_TEST_VAULT=obsidian-mcp-testvault uv run pytest -m obsidian
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, Tool

from obsidian_brain.obsidian import ObsidianCLI, find_cli_binary
from obsidian_brain.server import server as real_server
from obsidian_brain.tools import daily, notes
from obsidian_brain.vault import Vault

from .fake_vault import FakeVault

_DELETE_FOLDER_JS = """
const folder = app.vault.getFolderByPath(input);
if (folder) await app.vault.delete(folder, true);
return null;
"""


@dataclass(frozen=True)
class Sandbox:
    """A per-test folder inside the test vault."""

    dir: str

    def path(self, name: str) -> str:
        return f"{self.dir}/{name}"


@pytest.fixture(scope="session")
def live_vault_name() -> str:
    name = os.environ.get("OBSIDIAN_TEST_VAULT", "")
    if not name:
        pytest.skip(
            "OBSIDIAN_TEST_VAULT is not set; live Obsidian tests need a disposable test vault"
        )
    if "testvault" not in name:
        pytest.fail(
            f"Refusing to run against vault {name!r}: OBSIDIAN_TEST_VAULT must name a disposable "
            "vault whose name contains 'testvault'",
            pytrace=False,
        )
    return name


@pytest.fixture(scope="session")
def session_folder(live_vault_name: str):
    """One uniquely named folder per pytest session, removed at the end."""
    folder = f"_obsidian-brain-tests-{uuid.uuid4().hex[:8]}"
    yield folder
    code = f"const input = {folder!r}; {_DELETE_FOLDER_JS}"
    subprocess.run(
        [find_cli_binary(), f"vault={live_vault_name}", "eval", f"code={code}"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=60,
        check=False,
    )


@pytest.fixture
def cli(live_vault_name: str) -> ObsidianCLI:
    return ObsidianCLI(vault=live_vault_name, timeout=20)


@pytest.fixture
def vault(cli: ObsidianCLI) -> Vault:
    return Vault(cli)


@pytest.fixture
async def sandbox(cli: ObsidianCLI, session_folder: str, request: pytest.FixtureRequest):
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name)[:50]
    box = Sandbox(f"{session_folder}/{slug}-{uuid.uuid4().hex[:6]}")
    yield box
    await cli.eval(_DELETE_FOLDER_JS, box.dir)


# --- the live harness: Vault-level and tool-level live tests share it ---------------------------


async def put(cli: ObsidianCLI, path: str, content: str | bytes) -> None:
    """Create a file with exact bytes, bypassing Vault (so tests do not trust the code under test)."""
    raw = content.encode() if isinstance(content, str) else content
    await cli.eval(
        """
        const parts = input.path.split('/');
        for (let i = 1; i < parts.length; i++) {
          const dir = parts.slice(0, i).join('/');
          if (!app.vault.getFolderByPath(dir)) await app.vault.createFolder(dir);
        }
        await app.vault.createBinary(input.path, new Uint8Array(input.bytes).buffer);
        return null;
        """,
        {"path": path, "bytes": list(raw)},
    )


async def eventually(check: Callable[[], Awaitable[None]], timeout: float = 15.0) -> None:
    """Retry an async assertion until it holds (Obsidian indexes and re-parses asynchronously)."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return await check()
        except AssertionError:
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(0.2)


@pytest.fixture
async def disk(cli: ObsidianCLI) -> Callable[[str], bytes]:
    """Read a vault file's raw bytes straight from the vault folder on disk."""
    base = Path(await cli.eval("return app.vault.adapter.basePath;"))
    return lambda path: (base / path).read_bytes()


@pytest.fixture
async def daily_config(cli: ObsidianCLI, sandbox: Sandbox):
    """Point the daily-notes core plugin at the sandbox, then restore its options object."""
    options = {
        "folder": f"{sandbox.dir}/Daily",
        "format": "YYYY/MM/YYYY-MM-DD",
        "template": f"{sandbox.dir}/Templates/Daily",
    }
    await put(
        cli,
        sandbox.path("Templates/Daily.md"),
        "# {{title}}\ndate={{date}} fmt={{date:dddd, MMMM D YYYY}} year={{date:YYYY}} time={{time:HH:mm}}"
        " t2={{ time }} untouched={{foo}}\n\n## Log\n",
    )
    await cli.eval(
        """
        const plugin = app.internalPlugins.getPluginById('daily-notes');
        globalThis.__brainTestDailyOptions = plugin.instance.options;
        plugin.instance.options = input;
        return null;
        """,
        options,
    )
    yield options
    await cli.eval(
        """
        const plugin = app.internalPlugins.getPluginById('daily-notes');
        plugin.instance.options = globalThis.__brainTestDailyOptions;
        delete globalThis.__brainTestDailyOptions;
        return null;
        """
    )


class Tools:
    """The real note and daily tools, called through an in-memory MCP client on the live vault."""

    def __init__(self, client: Client, sandbox: Sandbox) -> None:
        self.client, self.sandbox = client, sandbox

    def p(self, name: str) -> str:
        return self.sandbox.path(name)

    async def call(self, tool: str, **args: Any) -> CallToolResult:
        return await self.client.call_tool(tool, args)

    async def ok(self, tool: str, **args: Any) -> dict[str, Any]:
        return data(await self.call(tool, **args))

    async def err(self, tool: str, **args: Any) -> str:
        return error_text(await self.call(tool, **args))

    async def put(self, name: str, content: str) -> str:
        return str((await self.ok("write_note", path=self.p(name), content=content))["path"])

    async def text(self, path: str) -> str:
        return str((await self.ok("get_note", path=path))["content"])


@asynccontextmanager
async def live_tools(
    vault: Vault, sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Tools]:
    """The real server's tools, their vault pointed at the test vault.

    Enter it inside the test body, not from a fixture: the MCP client's task group must be
    entered and exited by the same task.
    """
    for module in (notes, daily):
        monkeypatch.setattr(module, "get_vault", lambda: vault)
    async with Client(real_server) as client:
        yield Tools(client, sandbox)


# --- the note and daily tools on an in-memory vault ---------------------------------------------


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeVault:
    """An empty in-memory vault that the note and daily tools (and `real_server`) talk to."""
    fake_vault = FakeVault()
    for module in (notes, daily):
        monkeypatch.setattr(module, "get_vault", lambda: fake_vault)
    return fake_vault


@pytest.fixture
def note_tools() -> MCPServer:
    app = MCPServer("test")
    notes.register(app)
    daily.register(app)
    return app


# --- helpers shared by the in-memory MCP client tests ------------------------------------------


async def call(server: MCPServer, tool: str, /, **args: Any) -> CallToolResult:
    async with Client(server) as client:
        return await client.call_tool(tool, args)


def data(result: CallToolResult) -> dict[str, Any]:
    """The structured content of a successful call."""
    assert not result.is_error, result.content
    assert isinstance(result.structured_content, dict)
    return result.structured_content


def error_text(result: CallToolResult) -> str:
    assert result.is_error
    return result.content[0].text  # type: ignore[union-attr]


async def tool_list(server: MCPServer) -> dict[str, Tool]:
    async with Client(server) as client:
        return {tool.name: tool for tool in (await client.list_tools()).tools}


async def read_resource(server: MCPServer, uri: str) -> tuple[str, str | None]:
    """Read a resource; a protocol error is re-raised as `MCPError` (not inside an ExceptionGroup)."""
    failure: MCPError | None = None
    async with Client(server) as client:
        try:
            contents = (await client.read_resource(uri)).contents[0]
        except MCPError as error:
            failure = error
    if failure:
        raise failure
    return contents.text, contents.mime_type  # type: ignore[union-attr]
