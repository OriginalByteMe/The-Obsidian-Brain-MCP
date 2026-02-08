"""
Session state management for Obsidian Brain hooks and tools.

Provides atomic read/write of session state stored in temp files.
State is keyed by session_id and persists for the duration of a
Claude Code session.
"""

import fcntl
import json
import os
from datetime import datetime
from pathlib import Path

STATE_DIR = Path("/tmp")


def get_state_path(session_id: str) -> Path:
    """Get the temp file path for a session's state."""
    return STATE_DIR / f"obsidian-brain-{session_id}.json"


def read_state(session_id: str) -> dict:
    """Read session state, returning defaults if no state exists."""
    path = get_state_path(session_id)
    if not path.exists():
        return _default_state(session_id)
    with open(path) as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            data = json.load(f)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return data


def write_state(session_id: str, state: dict) -> None:
    """Write session state atomically with file locking."""
    path = get_state_path(session_id)
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(state, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _default_state(session_id: str) -> dict:
    """Return default state for a new session."""
    now = datetime.now().isoformat()
    return {
        "session_id": session_id,
        "started_at": now,
        "last_checkin": now,
        "notes_created": [],
        "daily_entries": [],
        "brag_entries": [],
    }


def read_vault_config(
    api_key: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> dict:
    """
    Read Obsidian Brain config from the vault via REST API.

    Uses environment variables as defaults:
    - OBSIDIAN_API_KEY
    - OBSIDIAN_HOST (default: 127.0.0.1)
    - OBSIDIAN_PORT (default: 27124)
    """
    import httpx

    api_key = api_key or os.getenv("OBSIDIAN_API_KEY", "")
    host = host or os.getenv("OBSIDIAN_HOST", "127.0.0.1")
    port = port or int(os.getenv("OBSIDIAN_PORT", "27124"))

    url = f"https://{host}:{port}/vault/Obsidian Brain/config.yml"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/markdown",
    }
    try:
        resp = httpx.get(url, headers=headers, verify=False, timeout=3.0)
        if resp.status_code == 200:
            import yaml

            return yaml.safe_load(resp.text) or {}
    except Exception:
        pass
    return {}


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
