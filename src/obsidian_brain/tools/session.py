"""
Session tracking tools for Obsidian Brain MCP.

Provides tools for session state management, plugin configuration,
and brag document maintenance. These tools are the foundation for
skills and hooks in the Claude Code plugin.
"""

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

import yaml

from ..client import NoteNotFoundError, ObsidianAPIError, ObsidianClient
from ..onboarding import CONFIG_PATH

if TYPE_CHECKING:
    from mcp_use.server import MCPServer

# Default plugin configuration (used when vault config is missing/incomplete)
DEFAULT_AUTONOMY = {
    "session_start_context": "silent",
    "session_end_learning_capture": "prompt",
    "session_end_daily_log": "silent",
    "brag_doc_update": "prompt",
    "periodic_checkin": "prompt",
}

DEFAULT_PLUGIN = {
    "checkin_interval_minutes": 30,
    "daily_note_heading": "## Claude Code Sessions",
    "brag_doc_path": None,
    "brag_doc_categories": [
        "Features Built",
        "Bugs Fixed",
        "Improvements",
        "Key Learnings",
    ],
    "learning_note_folder": None,
    "session_log_format": "summary",
}

# In-process session state (keyed by a synthetic session concept)
_session_state: dict = {
    "started_at": datetime.now().isoformat(),
    "notes_created": [],
    "daily_entries": [],
    "brag_entries": [],
}


def _merge_config(vault_config: dict) -> dict:
    """Merge vault config with defaults, filling missing keys."""
    autonomy = {**DEFAULT_AUTONOMY, **vault_config.get("autonomy", {})}
    plugin = {**DEFAULT_PLUGIN, **vault_config.get("plugin", {})}
    return {
        **vault_config,
        "autonomy": autonomy,
        "plugin": plugin,
    }


def _set_nested(data: dict, key: str, value: str) -> dict:
    """Set a value in a nested dict using dot-notation key."""
    keys = key.split(".")
    current = data
    for k in keys[:-1]:
        if k not in current or not isinstance(current[k], dict):
            current[k] = {}
        current = current[k]
    # Try to parse value as YAML for proper types (int, bool, None, list)
    try:
        parsed = yaml.safe_load(value)
    except (yaml.YAMLError, ValueError):
        parsed = value
    current[keys[-1]] = parsed
    return data


def register_session_tools(server: "MCPServer") -> None:
    """Register session tracking tools with the MCP server."""

    @server.tool()
    async def get_brain_config() -> str:
        """
        Get the current Obsidian Brain plugin configuration.

        Returns the autonomy settings, daily note heading, brag doc path,
        and other plugin preferences from .obsidian-brain/config.yml,
        merged with defaults for any missing keys.
        """
        async with ObsidianClient() as client:
            try:
                data = await client.get_note(CONFIG_PATH, include_metadata=False)
                vault_config = yaml.safe_load(data.get("content", "")) or {}
            except NoteNotFoundError:
                vault_config = {}
            except ObsidianAPIError:
                vault_config = {}

        merged = _merge_config(vault_config)
        return json.dumps({
            "success": True,
            "config": merged,
            "source": "vault" if vault_config else "defaults",
        })

    @server.tool()
    async def update_brain_config(key: str, value: str) -> str:
        """
        Update a specific plugin configuration value.

        Reads the current config from the vault, updates the specified key,
        and writes it back. Creates the config file if it doesn't exist.

        Args:
            key: Dot-notation config key (e.g., "autonomy.brag_doc_update")
            value: New value (e.g., "silent", "prompt", "disabled", "30")
        """
        async with ObsidianClient() as client:
            # Read existing config
            try:
                data = await client.get_note(CONFIG_PATH, include_metadata=False)
                vault_config = yaml.safe_load(data.get("content", "")) or {}
            except NoteNotFoundError:
                vault_config = {
                    "version": "1.0",
                    "created": datetime.now().isoformat(),
                }
            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

            # Update the key
            vault_config = _set_nested(vault_config, key, value)

            # Write back
            try:
                config_yaml = yaml.dump(
                    vault_config, default_flow_style=False, sort_keys=False
                )
                await client.create_note(CONFIG_PATH, config_yaml)
            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

        return json.dumps({
            "success": True,
            "key": key,
            "value": value,
            "message": f"Updated {key} to {value}",
        })

    @server.tool()
    async def get_session_state() -> str:
        """
        Get the current session tracking state.

        Returns notes created this session, daily note entries made,
        brag doc entries, and session start time. Used by skills to
        check for duplicates before creating entries.
        """
        # Try to read from temp file if session_id is available
        session_id = os.getenv("SESSION_ID", "")
        if session_id:
            import fcntl
            from pathlib import Path

            state_path = Path("/tmp") / f"obsidian-brain-{session_id}.json"
            if state_path.exists():
                try:
                    with open(state_path) as f:
                        fcntl.flock(f, fcntl.LOCK_SH)
                        try:
                            state = json.load(f)
                        finally:
                            fcntl.flock(f, fcntl.LOCK_UN)
                    return json.dumps({"success": True, "state": state})
                except (json.JSONDecodeError, OSError):
                    pass

        # Fall back to in-process state
        return json.dumps({"success": True, "state": _session_state})

    @server.tool()
    async def record_session_activity(
        activity_type: str,
        summary: str,
        note_paths: list[str] | None = None,
    ) -> str:
        """
        Record an activity in the session state and optionally in the daily note.

        Tracks what the plugin has done this session to prevent duplication.
        Activities are stored in the session state and can be reviewed later.

        Args:
            activity_type: Type of activity (note_created, learning_captured,
                          session_reviewed, brag_updated)
            summary: Brief description of what happened
            note_paths: Paths of notes created/modified
        """
        note_paths = note_paths or []
        timestamp = datetime.now().strftime("%H:%M")
        entry = f"[{timestamp}] {activity_type}: {summary}"

        # Update in-process state
        _session_state["daily_entries"].append(entry)
        for path in note_paths:
            if path not in _session_state["notes_created"]:
                _session_state["notes_created"].append(path)

        # Also update temp file if session_id available
        session_id = os.getenv("SESSION_ID", "")
        if session_id:
            import fcntl
            from pathlib import Path

            state_path = Path("/tmp") / f"obsidian-brain-{session_id}.json"
            try:
                if state_path.exists():
                    with open(state_path) as f:
                        fcntl.flock(f, fcntl.LOCK_SH)
                        try:
                            state = json.load(f)
                        finally:
                            fcntl.flock(f, fcntl.LOCK_UN)
                else:
                    state = {
                        "session_id": session_id,
                        "started_at": datetime.now().isoformat(),
                        "last_checkin": datetime.now().isoformat(),
                        "notes_created": [],
                        "daily_entries": [],
                        "brag_entries": [],
                    }

                state["daily_entries"].append(entry)
                for path in note_paths:
                    if path not in state["notes_created"]:
                        state["notes_created"].append(path)

                with open(state_path, "w") as f:
                    fcntl.flock(f, fcntl.LOCK_EX)
                    try:
                        json.dump(state, f, indent=2)
                    finally:
                        fcntl.flock(f, fcntl.LOCK_UN)
            except (json.JSONDecodeError, OSError):
                pass

        return json.dumps({
            "success": True,
            "activity_type": activity_type,
            "summary": summary,
            "note_paths": note_paths,
            "entry": entry,
            "message": f"Recorded: {entry}",
        })

    @server.tool()
    async def append_to_brag_doc(
        category: str,
        description: str,
        links: list[str] | None = None,
    ) -> str:
        """
        Add an entry to the brag document.

        Finds or creates the brag doc, checks for duplicate entries,
        and appends under the correct category heading.

        Args:
            category: One of "Features Built", "Bugs Fixed",
                     "Improvements", "Key Learnings"
            description: Brief description of the accomplishment
            links: Optional note names to wikilink (e.g., ["Auth Cache Fix"])
        """
        links = links or []
        today = datetime.now().strftime("%Y-%m-%d")

        # Read config to find brag doc path
        async with ObsidianClient() as client:
            try:
                config_data = await client.get_note(
                    CONFIG_PATH, include_metadata=False
                )
                vault_config = yaml.safe_load(config_data.get("content", "")) or {}
            except (NoteNotFoundError, ObsidianAPIError):
                vault_config = {}

            merged = _merge_config(vault_config)
            brag_path = merged["plugin"].get("brag_doc_path")
            categories = merged["plugin"].get("brag_doc_categories", [])

            # Auto-detect brag doc if path not configured
            if not brag_path:
                try:
                    results = await client.search_simple("brag doc", context_length=50)
                    for result in results:
                        path = result.get("filename", "")
                        if path.endswith(".md"):
                            brag_path = path
                            break
                except ObsidianAPIError:
                    pass

            # If still no path, create a default one
            if not brag_path:
                org_systems = vault_config.get("vault_profile", {}).get(
                    "organizational_systems", []
                )
                if "PARA Method" in org_systems:
                    brag_path = "Areas/Career/Brag Doc.md"
                elif "Zettelkasten" in org_systems:
                    brag_path = "Permanent/Brag Doc.md"
                else:
                    brag_path = "Obsidian Brain/Brag Doc.md"

            # Read or create brag doc
            try:
                data = await client.get_note(brag_path, include_metadata=False)
                content = data.get("content", "")
            except NoteNotFoundError:
                # Create new brag doc
                category_headings = "\n\n".join(
                    f"## {cat}" for cat in (categories or list(DEFAULT_PLUGIN["brag_doc_categories"]))
                )
                content = (
                    "---\n"
                    "tags: [brag-doc, career]\n"
                    f"updated: {today}\n"
                    "brain-managed: true\n"
                    "---\n\n"
                    "# Brag Doc\n\n"
                    "> Accomplishments automatically tracked by Obsidian Brain.\n"
                    "> Entries are added as you work - review and curate periodically.\n\n"
                    f"{category_headings}\n"
                )
            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

            # Check for duplicates (same date + similar description)
            if description in content:
                return json.dumps({
                    "success": True,
                    "action": "skipped",
                    "message": f"Entry already exists in brag doc: {description}",
                    "brag_doc_path": brag_path,
                })

            # Build the entry line
            link_text = " ".join(f"[[{link}]]" for link in links)
            entry_line = f"- **{today}**: {description}"
            if link_text:
                entry_line += f" {link_text}"

            # Find the category heading and insert after it
            heading = f"## {category}"
            if heading in content:
                # Insert after the heading line
                lines = content.split("\n")
                new_lines = []
                inserted = False
                for line in lines:
                    new_lines.append(line)
                    if not inserted and line.strip() == heading:
                        new_lines.append("")
                        new_lines.append(entry_line)
                        inserted = True
                content = "\n".join(new_lines)
            else:
                # Category heading doesn't exist, append it
                content += f"\n\n{heading}\n\n{entry_line}\n"

            # Update the 'updated' frontmatter
            content = content.replace(
                f"updated: {content.split('updated: ')[1].split(chr(10))[0]}" if "updated: " in content else "",
                f"updated: {today}" if "updated: " in content else "",
                1,
            )

            # Write back
            try:
                await client.create_note(brag_path, content)
            except ObsidianAPIError as e:
                return json.dumps({
                    "error": True,
                    "type": "ObsidianAPIError",
                    "message": str(e),
                })

            # Track in session state
            _session_state["brag_entries"].append(description)

        return json.dumps({
            "success": True,
            "action": "appended",
            "category": category,
            "description": description,
            "brag_doc_path": brag_path,
            "message": f"Added to brag doc under '{category}': {description}",
        })
