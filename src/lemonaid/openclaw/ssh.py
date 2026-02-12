"""SSH utilities for remote OpenClaw session discovery.

These functions are used at registration time to find and inspect
sessions on a remote host. They are NOT called in the hot polling
loop — the watcher uses _read_jsonl_tail_ssh in watcher.py instead.
"""

from __future__ import annotations

import json
import re
import subprocess

from ..log import get_logger
from .utils import _extract_text_from_content

_log = get_logger("openclaw.ssh")

_UUID_RE = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


def _ssh_run(host: str, command: str, timeout: int = 10) -> str | None:
    """Run a command on a remote host via SSH. Returns stdout or None on failure."""
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", host, command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            _log.debug("ssh command failed on %s: %s", host, result.stderr.strip())
            return None
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError) as e:
        _log.warning("ssh error on %s: %s", host, e)
        return None


def read_session_header(host: str, path: str) -> dict | None:
    """Read the session header (first line) from a remote session file."""
    output = _ssh_run(host, f"head -1 '{path}'")
    if not output:
        return None
    try:
        entry = json.loads(output)
        if entry.get("type") == "session":
            return entry
    except json.JSONDecodeError:
        pass
    return None


def find_most_recent_session(
    host: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Find the most recently modified session file on a remote host.

    Returns (session_path, session_id, agent_id, cwd) or all Nones.
    """
    output = _ssh_run(host, "ls -t ~/.openclaw/agents/*/sessions/*.jsonl 2>/dev/null | head -1")
    if not output:
        _log.info("no sessions found on %s", host)
        return None, None, None, None

    session_path = output.strip()
    _log.info("most recent session on %s: %s", host, session_path)

    # Extract agent_id from path: .../agents/<agent_id>/sessions/<file>.jsonl
    parts = session_path.split("/")
    agent_id = None
    for i, part in enumerate(parts):
        if part == "agents" and i + 1 < len(parts):
            agent_id = parts[i + 1]
            break

    # Extract session_id from filename
    filename = parts[-1] if parts else ""
    match = _UUID_RE.search(filename)
    session_id = match.group(1) if match else None

    if not session_id:
        _log.warning("could not extract session_id from %s", filename)
        return None, None, None, None

    # Read header for cwd
    header = read_session_header(host, session_path)
    session_cwd = header.get("cwd") if header else None

    return session_path, session_id, agent_id, session_cwd


def get_session_name(host: str, agent_id: str, session_id: str) -> str | None:
    """Get the display name for a session from the remote sessions.json index.

    Priority: label > last segment of session key.
    """
    output = _ssh_run(host, f"cat ~/.openclaw/agents/{agent_id}/sessions/sessions.json")
    if not output:
        return None

    try:
        index = json.loads(output)
    except json.JSONDecodeError:
        return None

    for session_key, session_data in index.items():
        if not isinstance(session_data, dict):
            continue

        data_id = session_data.get("sessionId") or session_data.get("id")
        if not data_id:
            continue

        if (
            data_id == session_id
            or data_id.startswith(session_id)
            or session_id.startswith(data_id[:8])
        ):
            label = session_data.get("label")
            if label:
                return label
            if ":" in session_key:
                return session_key.rsplit(":", 1)[-1]
            return session_key

    return None


def get_session_key(host: str, agent_id: str, session_id: str) -> str | None:
    """Get the session key for resuming from the remote sessions.json index."""
    output = _ssh_run(host, f"cat ~/.openclaw/agents/{agent_id}/sessions/sessions.json")
    if not output:
        return None

    try:
        index = json.loads(output)
    except json.JSONDecodeError:
        return None

    for session_key, session_data in index.items():
        if not isinstance(session_data, dict):
            continue
        data_id = session_data.get("sessionId") or session_data.get("id")
        if not data_id:
            continue
        if (
            data_id == session_id
            or data_id.startswith(session_id)
            or session_id.startswith(data_id[:8])
        ):
            return session_key

    return None


def get_last_user_message(host: str, path: str, max_bytes: int = 64 * 1024) -> str | None:
    """Get the last user message from a remote session file."""
    output = _ssh_run(host, f"tail -c {max_bytes} '{path}'")
    if not output:
        return None

    lines = output.strip().split("\n")

    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if entry.get("type") != "message":
            continue

        msg = entry.get("message", {})
        role = entry.get("role") or msg.get("role")
        if role == "user":
            content = entry.get("content") or msg.get("content", [])
            text = _extract_text_from_content(content)
            if text:
                return text[:77] + "..." if len(text) > 80 else text

    return None
