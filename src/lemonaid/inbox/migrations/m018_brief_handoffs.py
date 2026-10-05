"""Durable requests and session relationships for harness handoff."""

import sqlite3

VERSION = 18
DESCRIPTION = "Add brief handoffs"


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS brief_handoffs (
            token TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            source TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT '',
            harness TEXT NOT NULL,
            phase TEXT NOT NULL,
            section_hash TEXT NOT NULL,
            session TEXT NOT NULL,
            source_window TEXT NOT NULL,
            source_window_id TEXT NOT NULL,
            source_pane_id TEXT NOT NULL,
            target_window TEXT NOT NULL DEFAULT '',
            target_window_id TEXT NOT NULL DEFAULT '',
            target_pane_id TEXT NOT NULL DEFAULT '',
            ready INTEGER NOT NULL DEFAULT 0,
            accepted INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            deadline REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS brief_handoffs_active_path
            ON brief_handoffs(path) WHERE phase NOT IN ('complete', 'failed');
        CREATE TABLE IF NOT EXISTS brief_handoff_sessions (
            path TEXT NOT NULL,
            channel TEXT PRIMARY KEY,
            generation INTEGER NOT NULL
        );
    """)
