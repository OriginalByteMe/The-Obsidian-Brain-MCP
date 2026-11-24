"""Onboarding tools: learn the vault's conventions once, then read them back each session."""

import asyncio
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from ..exceptions import NoteNotFoundError
from ..knowledge import KNOWLEDGE_BASE_PATH, KnowledgeBaseStatus, knowledge_base_status
from ..memory import BRAIN_DIR, MEMORIES_PATH, utc_now
from ..models import Note
from ..onboarding import (
    CONFIG_PATH,
    CONVENTIONS_PATH,
    OVERVIEW_PATH,
    VaultAnalysis,
    analyze_vault,
    extract_yaml_body,
    render_config,
    render_conventions,
    render_overview,
)
from ..vault import Vault, get_vault
from .notes import DESTRUCTIVE, READ_ONLY


class VaultConfig(BaseModel):
    onboarded: bool = Field(description="True when Obsidian Brain/config.md exists.")
    partial: bool = Field(
        description="True when Obsidian Brain/ exists but config.md does not (setup unfinished)."
    )
    config_path: str
    config: str | None = Field(
        description="The vault profile as YAML text: the content of the first ```yaml fence in "
        "config.md, or the whole file when it has none. Null when not onboarded."
    )
    memories: int = Field(description="Memory files under Obsidian Brain/memories/.")
    knowledge_base: KnowledgeBaseStatus
    recommendation: str = Field(description="The next step this vault needs.")


class OnboardingResult(BaseModel):
    created: list[str] = Field(description="Files written for the first time.")
    overwritten: list[str] = Field(description="Existing files replaced (only with force=true).")
    kept: list[str] = Field(
        description="Existing files left untouched, so your edits survive. "
        "Pass force=true to regenerate them."
    )
    analysis: VaultAnalysis
    next_steps: list[str]


async def _read_if_listed(vault: Vault, listed: set[str], path: str) -> Note | None:
    return await vault.read_note(path) if path in listed else None


def register(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY)
    async def get_vault_config() -> VaultConfig:
        """Read the vault profile, and see whether onboarding and the knowledge base exist.

        Start here each session. Use run_onboarding when `onboarded` is false, list_memories
        for the notes saved across sessions, build_knowledge_base for a whole-vault overview.
        Example: get_vault_config()
        """
        vault = get_vault()
        try:
            listed = {f.path for f in await vault.list_files(BRAIN_DIR)}
        except NoteNotFoundError:
            listed = set()
        config, kb = await asyncio.gather(
            _read_if_listed(vault, listed, CONFIG_PATH),
            _read_if_listed(vault, listed, KNOWLEDGE_BASE_PATH),
        )
        if config:
            recommendation = (
                "Ready. Call list_memories and read the ones relevant to the task."
                if kb
                else "Ready. Optionally call build_knowledge_base for a whole-vault overview."
            )
        elif listed:
            recommendation = "Obsidian Brain/ exists without config.md. Call run_onboarding."
        else:
            recommendation = "Not onboarded. Call run_onboarding to profile the vault."
        return VaultConfig(
            onboarded=config is not None,
            partial=bool(listed) and config is None,
            config_path=CONFIG_PATH,
            config=extract_yaml_body(config.content) if config else None,
            memories=sum(1 for p in listed if p.startswith(f"{MEMORIES_PATH}/")),
            knowledge_base=knowledge_base_status(kb.frontmatter if kb else None),
            recommendation=recommendation,
        )

    @server.tool(annotations=DESTRUCTIVE)
    async def run_onboarding(
        force: Annotated[
            bool,
            Field(
                description="False (default): write only the files that do not exist yet, so "
                "hand-edited config and memories survive. True: regenerate all three, "
                "overwriting any edits."
            ),
        ] = False,
    ) -> OnboardingResult:
        """Profile the vault (folder system, tags, frontmatter, naming) and save what it found.

        Writes Obsidian Brain/config.md and the memories vault-overview and conventions. Files
        that already exist are kept unless force is true. The analysis ignores Obsidian Brain/
        itself. Use get_vault_config to read the result, write_memory to add your own notes,
        build_knowledge_base for the full vault map.
        Example: run_onboarding()
        """
        vault = get_vault()
        snapshot = await vault.snapshot()
        existing = {n.path for n in snapshot.notes}
        analysis = analyze_vault(snapshot)
        now = utc_now()
        files = {
            CONFIG_PATH: render_config(analysis, now),
            OVERVIEW_PATH: render_overview(analysis, now),
            CONVENTIONS_PATH: render_conventions(analysis, now),
        }
        created: list[str] = []
        overwritten: list[str] = []
        kept: list[str] = []
        for path, text in files.items():  # one at a time: the first write creates the folders
            if path not in existing:
                await vault.write_note(path, text)
                created.append(path)
            elif force:
                await vault.write_note(path, text, overwrite=True)
                overwritten.append(path)
            else:
                kept.append(path)
        return OnboardingResult(
            created=created,
            overwritten=overwritten,
            kept=kept,
            analysis=analysis,
            next_steps=[
                f"Review {CONFIG_PATH} and correct anything the analysis got wrong.",
                "Call list_memories and read_memory to use the starter memories.",
                "Call write_memory to record what you learn about the vault.",
            ],
        )
