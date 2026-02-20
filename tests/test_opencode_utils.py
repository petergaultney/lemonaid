"""Tests for lemonaid.opencode.utils module."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from lemonaid.opencode import utils


def test_get_session_schema_without_data_column(tmp_path: Path):
    db_path = tmp_path / "opencode.db"
    session_id = "ses_123"

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT, directory TEXT)")
        conn.execute(
            "INSERT INTO session (id, title, directory) VALUES (?, ?, ?)",
            (session_id, "My Session", "/tmp/project"),
        )
        conn.commit()

    with patch("lemonaid.opencode.utils.get_db_path", return_value=db_path):
        session = utils._get_session(session_id)

    assert session == {
        "id": session_id,
        "title": "My Session",
        "directory": "/tmp/project",
        "data": {},
    }


def test_get_cwd_and_name_with_data_column(tmp_path: Path):
    db_path = tmp_path / "opencode.db"
    session_id = "ses_456"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT, directory TEXT, data TEXT)"
        )
        conn.execute(
            "INSERT INTO session (id, title, directory, data) VALUES (?, ?, ?, ?)",
            (session_id, "Named", "", json.dumps({"path": {"cwd": "/tmp/from-data"}})),
        )
        conn.commit()

    with patch("lemonaid.opencode.utils.get_db_path", return_value=db_path):
        cwd, name = utils.get_cwd_and_name(session_id)

    assert cwd == "/tmp/from-data"
    assert name == "Named"
