#!/usr/bin/env python3
"""
Periodic check-in hook for Obsidian Brain.

Fires on Stop events — checks if enough time has passed since the last
check-in and suggests capturing notes if the interval has been reached.

Input (stdin): JSON with session_id, hook_event_name
Output (stdout): JSON with hookSpecificOutput.additionalContext, or empty (no-op)
"""

import json
import os
import sys
from datetime import datetime

# Add scripts dir to path for brain_state import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_state


def main():
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    if not session_id:
        sys.exit(0)

    # Read config
    config = brain_state.read_vault_config()
    autonomy = {**brain_state.DEFAULT_AUTONOMY, **config.get("autonomy", {})}
    plugin = {**brain_state.DEFAULT_PLUGIN, **config.get("plugin", {})}

    # Check if periodic check-in is disabled
    if autonomy.get("periodic_checkin") == "disabled":
        sys.exit(0)

    # Read session state
    state = brain_state.read_state(session_id)

    # Calculate time since last check-in
    last_checkin_str = state.get("last_checkin", "")
    if not last_checkin_str:
        sys.exit(0)

    try:
        last_checkin = datetime.fromisoformat(last_checkin_str)
    except ValueError:
        sys.exit(0)

    now = datetime.now()
    elapsed_minutes = (now - last_checkin).total_seconds() / 60
    interval = plugin.get("checkin_interval_minutes", 30)

    # If interval not reached, exit silently (fast path)
    if elapsed_minutes < interval:
        sys.exit(0)

    # Interval reached — update last_checkin and output prompt
    state["last_checkin"] = now.isoformat()
    brain_state.write_state(session_id, state)

    context = (
        "It's been a while since we last checked in. "
        "Is there anything from this session worth noting down? You can:\n"
        "- /capture-learning to record what you've learned\n"
        "- /document-it to document something you're working on\n"
        "- Or just say 'nothing for now' to continue"
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": context,
        }
    }
    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
