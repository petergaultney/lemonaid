"""OpenClaw session utilities."""

from __future__ import annotations

import json
import re
from pathlib import Path


def get_agents_root() -> Path:
    """Return the OpenClaw agents root directory."""
    return Path.home() / ".openclaw" / "agents"


def get_sessions_root(agent_id: str) -> Path:
    """Return the sessions directory for an agent."""
    return get_agents_root() / agent_id / "sessions"


def extract_session_id_from_filename(name: str) -> str | None:
    """Extract a session UUID from an OpenClaw session filename.

    OpenClaw uses UUID-style session IDs like:
    a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl
    """
    match = re.search(
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        name,
    )
    if match:
        return match.group(1)
    return None


def read_session_header(path: Path) -> dict | None:
    """Read the session header from a session file.

    OpenClaw session files have a header line with type: "session"
    containing id, cwd, timestamp, and optional parentSession.
    """
    try:
        with path.open() as f:
            line = f.readline()
            if not line:
                return None

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                return None

            if entry.get("type") == "session":
                return entry
    except OSError:
        return None

    return None


def find_session_path(session_id: str, agent_id: str | None = None) -> Path | None:
    """Find an OpenClaw session file by session ID.

    If agent_id is provided, search only that agent's sessions.
    Otherwise, search all agents.
    """
    if not session_id:
        return None

    agents_root = get_agents_root()
    if not agents_root.exists():
        return None

    if agent_id:
        # Search specific agent
        sessions_dir = get_sessions_root(agent_id)
        if sessions_dir.exists():
            for path in sessions_dir.glob(f"*{session_id}.jsonl"):
                if path.is_file():
                    return path
            # Try partial match
            if len(session_id) >= 8:
                for path in sessions_dir.glob("*.jsonl"):
                    if session_id[:8] in path.name:
                        return path
    else:
        # Search all agents
        for agent_dir in agents_root.iterdir():
            if not agent_dir.is_dir():
                continue

            sessions_dir = agent_dir / "sessions"
            if not sessions_dir.exists():
                continue

            for path in sessions_dir.glob(f"*{session_id}.jsonl"):
                if path.is_file():
                    return path

            # Try partial match
            if len(session_id) >= 8:
                for path in sessions_dir.glob("*.jsonl"):
                    if session_id[:8] in path.name:
                        return path

    return None


def discover_agents() -> list[str]:
    """Discover all agent IDs with sessions."""
    agents_root = get_agents_root()
    if not agents_root.exists():
        return []

    agents = []
    for agent_dir in agents_root.iterdir():
        if not agent_dir.is_dir():
            continue

        sessions_json = agent_dir / "sessions" / "sessions.json"
        if sessions_json.exists():
            agents.append(agent_dir.name)

    return agents


def read_sessions_index(agent_id: str) -> dict | None:
    """Read the sessions.json index for an agent."""
    sessions_json = get_sessions_root(agent_id) / "sessions.json"
    if not sessions_json.exists():
        return None

    try:
        return json.loads(sessions_json.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def get_session_name(agent_id: str, session_id: str) -> str | None:
    """Get the display name for a session from the sessions.json index.

    OpenClaw's sessions.json uses session keys like "agent:main:testing-session"
    as top-level keys, with optional "label" field for user-assigned names.
    Each session object has a "sessionId" field with the UUID.

    Priority: label > last segment of session key
    """
    index = read_sessions_index(agent_id)
    if not index:
        return None

    # sessions.json has session keys as top-level keys (not a "sessions" array)
    # e.g., {"agent:main:main": {"sessionId": "abc-123", "label": "My Session", ...}}
    for session_key, session_data in index.items():
        if not isinstance(session_data, dict):
            continue

        # Match by sessionId field (the UUID we have)
        data_id = session_data.get("sessionId") or session_data.get("id")
        if not data_id:
            continue

        # Check if our session_id matches (could be full UUID or prefix)
        if (
            data_id == session_id
            or data_id.startswith(session_id)
            or session_id.startswith(data_id[:8])
        ):
            # Priority: label > last segment of session key
            label = session_data.get("label")
            if label:
                return label

            # Extract last segment from session key (e.g., "testing-session" from "agent:main:testing-session")
            if ":" in session_key:
                return session_key.rsplit(":", 1)[-1]

            return session_key

    return None


def get_last_user_message(session_path: Path, max_bytes: int = 64 * 1024) -> str | None:
    """Get the last user message from a session file.

    Reads the tail of the file and finds the most recent user message.
    Returns the message text (truncated if long), or None if not found.
    """
    try:
        file_size = session_path.stat().st_size
        read_size = min(file_size, max_bytes)

        with open(session_path, encoding="utf-8", errors="replace") as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                f.readline()  # Skip partial line
            content = f.read()

        lines = content.strip().split("\n")

        # Search from end for user message
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type")

            if entry_type == "message":
                msg = entry.get("message", {})
                role = entry.get("role") or msg.get("role")
                if role == "user":
                    # Extract text content
                    content = entry.get("content") or msg.get("content", [])
                    text = _extract_text_from_content(content)
                    if text:
                        # Truncate if long
                        if len(text) > 80:
                            return text[:77] + "..."
                        return text

    except OSError:
        pass

    return None


def _extract_text_from_content(content: list | str) -> str | None:
    """Extract text from message content (handles string or content blocks)."""
    if isinstance(content, str):
        return content.strip() if content.strip() else None

    if not isinstance(content, list):
        return None

    for block in content:
        if isinstance(block, str):
            if block.strip():
                return block.strip()
        elif isinstance(block, dict):
            block_type = block.get("type")
            if block_type in ("text", "input_text"):
                text = block.get("text", "")
                if text.strip():
                    return text.strip()

    return None


def find_recent_session_for_cwd(cwd: str) -> tuple[Path | None, str | None, str | None]:
    """Find the most recently modified session file for a given cwd.

    Scans all agents' session files and returns the one most recently modified
    that matches the given working directory.

    Returns (session_path, session_id, agent_id) or (None, None, None).
    """
    agents_root = get_agents_root()
    if not agents_root.exists():
        return None, None, None

    # Normalize cwd for comparison
    cwd = str(Path(cwd).resolve())

    best_match: tuple[Path, str, str, float] | None = None

    for agent_dir in agents_root.iterdir():
        if not agent_dir.is_dir():
            continue

        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.exists():
            continue

        for session_path in sessions_dir.glob("*.jsonl"):
            if not session_path.is_file():
                continue

            # Read header to check cwd
            header = read_session_header(session_path)
            if not header:
                continue

            session_cwd = header.get("cwd")
            if not session_cwd:
                continue

            # Normalize and compare
            if str(Path(session_cwd).resolve()) != cwd:
                continue

            # Get modification time
            mtime = session_path.stat().st_mtime

            # Extract session ID
            session_id = header.get("id") or extract_session_id_from_filename(session_path.name)
            if not session_id:
                continue

            if best_match is None or mtime > best_match[3]:
                best_match = (session_path, session_id, agent_dir.name, mtime)

    if best_match:
        return best_match[0], best_match[1], best_match[2]

    return None, None, None


def find_most_recent_session() -> tuple[Path | None, str | None, str | None, str | None]:
    """Find the most recently modified session file across all agents.

    Returns (session_path, session_id, agent_id, cwd) or (None, None, None, None).
    """
    agents_root = get_agents_root()
    if not agents_root.exists():
        return None, None, None, None

    best_match: tuple[Path, str, str, str, float] | None = None

    for agent_dir in agents_root.iterdir():
        if not agent_dir.is_dir():
            continue

        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.exists():
            continue

        for session_path in sessions_dir.glob("*.jsonl"):
            if not session_path.is_file():
                continue

            # Get modification time
            mtime = session_path.stat().st_mtime

            # Read header
            header = read_session_header(session_path)
            if not header:
                continue

            # Extract session ID
            session_id = header.get("id") or extract_session_id_from_filename(session_path.name)
            if not session_id:
                continue

            session_cwd = header.get("cwd", "")

            if best_match is None or mtime > best_match[4]:
                best_match = (session_path, session_id, agent_dir.name, session_cwd, mtime)

    if best_match:
        return best_match[0], best_match[1], best_match[2], best_match[3]

    return None, None, None, None
