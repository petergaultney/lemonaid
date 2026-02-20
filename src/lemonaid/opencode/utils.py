"""OpenCode session utilities."""

import json
import sqlite3
from pathlib import Path


def get_db_path() -> Path:
    """Return the OpenCode SQLite database path."""
    return Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _get_session(session_id: str) -> dict | None:
    """Get OpenCode session row by id, parsing JSON fields."""
    if not session_id:
        return None

    db_path = get_db_path()
    if not db_path.exists():
        return None

    try:
        with sqlite3.connect(db_path) as conn:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(session)").fetchall()}
            has_data = "data" in columns
            query = (
                "SELECT id, title, directory, data FROM session WHERE id = ?"
                if has_data
                else "SELECT id, title, directory FROM session WHERE id = ?"
            )
            row = conn.execute(query, (session_id,)).fetchone()
    except sqlite3.Error:
        return None

    if not row:
        return None

    data = {}
    if len(row) > 3:
        data_raw = row[3]
        if isinstance(data_raw, str) and data_raw:
            try:
                data = json.loads(data_raw)
            except json.JSONDecodeError:
                data = {}

    return {
        "id": row[0],
        "title": row[1],
        "directory": row[2],
        "data": data,
    }


def get_cwd_and_name(session_id: str) -> tuple[str | None, str | None]:
    """Resolve cwd and display name for an OpenCode session id."""
    session = _get_session(session_id)
    if not session:
        return None, None

    directory = session.get("directory")
    data = session.get("data", {})

    cwd = directory or data.get("directory") or data.get("path", {}).get("cwd")
    name = session.get("title")
    return cwd, name
