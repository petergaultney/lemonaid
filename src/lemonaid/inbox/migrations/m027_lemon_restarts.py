"""Durable restart operations and native process registrations."""

import sqlite3

VERSION = 27
DESCRIPTION = "Record lemon restarts and harness generations"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE lemon_restarts (
        token TEXT PRIMARY KEY, channel TEXT NOT NULL, phase TEXT NOT NULL,
        created REAL NOT NULL, deadline REAL NOT NULL, plan TEXT NOT NULL,
        evidence TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '')""")
    conn.execute("""CREATE UNIQUE INDEX one_restart_per_channel ON lemon_restarts(channel)
        WHERE phase NOT IN ('complete', 'failed', 'partial')""")
    conn.execute("""CREATE TABLE harness_generations (
        channel TEXT PRIMARY KEY, session_id TEXT NOT NULL, identity TEXT NOT NULL,
        settings TEXT NOT NULL, token TEXT NOT NULL, registered REAL NOT NULL)""")
