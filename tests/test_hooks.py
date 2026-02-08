"""Tests for hook scripts."""

import json
import os
import subprocess

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")


def run_hook(script_name: str, input_data: dict, env_override: dict | None = None) -> tuple[str, str, int]:
    """Run a hook script with mock stdin input.

    Returns (stdout, stderr, returncode).
    """
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    env = {**os.environ, **(env_override or {})}

    result = subprocess.run(
        ["python3", script_path],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


class TestSessionStartHook:
    """Tests for session-start.py hook script."""

    def test_outputs_valid_json(self):
        """Session-start outputs valid JSON with additionalContext."""
        stdout, stderr, rc = run_hook(
            "session-start.py",
            {"session_id": "test-hook-1", "hook_event_name": "SessionStart"},
        )

        assert rc == 0
        data = json.loads(stdout)
        assert "hookSpecificOutput" in data
        assert "additionalContext" in data["hookSpecificOutput"]
        assert "Brain connected" in data["hookSpecificOutput"]["additionalContext"]

    def test_initializes_state_file(self):
        """Session-start creates a session state temp file."""
        session_id = "test-hook-init"
        state_path = f"/tmp/obsidian-brain-{session_id}.json"

        # Clean up any leftover state
        if os.path.exists(state_path):
            os.unlink(state_path)

        run_hook(
            "session-start.py",
            {"session_id": session_id, "hook_event_name": "SessionStart"},
        )

        assert os.path.exists(state_path)
        with open(state_path) as f:
            state = json.load(f)
        assert state["session_id"] == session_id
        assert "started_at" in state

        # Clean up
        os.unlink(state_path)

    def test_handles_invalid_json_input(self):
        """Session-start exits gracefully on invalid JSON."""
        script_path = os.path.join(SCRIPTS_DIR, "session-start.py")
        result = subprocess.run(
            ["python3", script_path],
            input="not valid json",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0


class TestPeriodicCheckinHook:
    """Tests for periodic-checkin.py hook script."""

    def test_returns_empty_when_interval_not_reached(self):
        """Periodic check-in exits silently when interval hasn't passed."""
        session_id = "test-checkin-short"

        # Create a fresh state file with recent last_checkin
        import sys
        sys.path.insert(0, SCRIPTS_DIR)
        import brain_state

        state = brain_state._default_state(session_id)
        brain_state.write_state(session_id, state)

        stdout, stderr, rc = run_hook(
            "periodic-checkin.py",
            {"session_id": session_id, "hook_event_name": "Stop"},
        )

        assert rc == 0
        assert stdout.strip() == ""  # No output = no-op

        # Clean up
        state_path = brain_state.get_state_path(session_id)
        if state_path.exists():
            state_path.unlink()

    def test_returns_prompt_when_interval_exceeded(self):
        """Periodic check-in returns prompt when interval has passed."""
        session_id = "test-checkin-long"

        import sys
        from datetime import datetime, timedelta
        sys.path.insert(0, SCRIPTS_DIR)
        import brain_state

        # Create state with last_checkin 60 minutes ago
        state = brain_state._default_state(session_id)
        state["last_checkin"] = (datetime.now() - timedelta(minutes=60)).isoformat()
        brain_state.write_state(session_id, state)

        stdout, stderr, rc = run_hook(
            "periodic-checkin.py",
            {"session_id": session_id, "hook_event_name": "Stop"},
        )

        assert rc == 0
        data = json.loads(stdout)
        assert "hookSpecificOutput" in data
        assert "check" in data["hookSpecificOutput"]["additionalContext"].lower()

        # Clean up
        state_path = brain_state.get_state_path(session_id)
        if state_path.exists():
            state_path.unlink()

    def test_handles_missing_session_id(self):
        """Periodic check-in exits gracefully with no session_id."""
        stdout, stderr, rc = run_hook(
            "periodic-checkin.py",
            {"hook_event_name": "Stop"},
        )

        assert rc == 0
        assert stdout.strip() == ""

    def test_handles_no_state_file(self):
        """Periodic check-in handles missing state file gracefully."""
        stdout, stderr, rc = run_hook(
            "periodic-checkin.py",
            {"session_id": "nonexistent-session-xyz", "hook_event_name": "Stop"},
        )

        assert rc == 0
        # Should exit silently — new session hasn't passed interval yet
        assert stdout.strip() == ""
