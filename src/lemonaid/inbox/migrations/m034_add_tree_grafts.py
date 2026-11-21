"""Lemons the grove draws on another lemon's tree, each by its Lemon-ID, else its channel."""

import sqlite3

VERSION = 34
DESCRIPTION = "Add tree_grafts table"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tree_grafts"
        " (lemon TEXT PRIMARY KEY, onto TEXT NOT NULL, grafted_at REAL NOT NULL)"
    )
