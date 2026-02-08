#!/usr/bin/env python3
"""
Session start hook for Obsidian Brain.

Fires on SessionStart — loads vault context and initializes session state.
Reads today's daily note and presents a context summary to Claude.

Input (stdin): JSON with session_id, cwd, hook_event_name
Output (stdout): JSON with hookSpecificOutput.additionalContext
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

    session_id = hook_input.get("session_id", "unknown")

    # Read vault config
    config = brain_state.read_vault_config()
    autonomy = {**brain_state.DEFAULT_AUTONOMY, **config.get("autonomy", {})}
    plugin = {**brain_state.DEFAULT_PLUGIN, **config.get("plugin", {})}

    # Check if session start context is disabled
    if autonomy.get("session_start_context") == "disabled":
        sys.exit(0)

    # Initialize session state
    state = brain_state._default_state(session_id)
    brain_state.write_state(session_id, state)

    # Try to read today's daily note
    daily_summary = ""
    api_key = os.getenv("OBSIDIAN_API_KEY", "")
    host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")
    port = int(os.getenv("OBSIDIAN_PORT", "27124"))

    if api_key:
        try:
            import ssl
            import urllib.request

            now = datetime.now()
            url = f"https://{host}:{port}/periodic/daily/{now.year}/{now.month:02d}/{now.day:02d}/"
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "text/markdown",
                },
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=3, context=ctx) as resp:
                status = resp.status
                resp_text = resp.read().decode("utf-8")
            if status == 200:
                content = resp_text
                # Extract section under configured heading
                heading = plugin.get("daily_note_heading", "## Claude Code Sessions")
                if heading in content:
                    section = content.split(heading, 1)[1]
                    # Take content until next heading or end
                    next_heading = section.find("\n## ")
                    if next_heading > 0:
                        section = section[:next_heading]
                    daily_summary = section.strip()
                    if daily_summary:
                        daily_summary = f"\n\nToday's sessions:\n{daily_summary}"
                elif content.strip():
                    # Just note that a daily note exists
                    daily_summary = "\n\nDaily note exists for today."
        except Exception:
            pass

    # Build context message
    parts = ["Brain connected to vault."]
    if daily_summary:
        parts.append(daily_summary)

    # Show autonomy config summary
    active_features = []
    if autonomy.get("session_end_learning_capture") != "disabled":
        active_features.append("learning capture")
    if autonomy.get("session_end_daily_log") != "disabled":
        active_features.append("daily log")
    if autonomy.get("brag_doc_update") != "disabled":
        active_features.append("brag doc")
    if autonomy.get("periodic_checkin") != "disabled":
        active_features.append("periodic check-in")

    if active_features:
        parts.append(f"\nActive: {', '.join(active_features)}")

    context = "\n".join(parts)

    # Output hook response
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
