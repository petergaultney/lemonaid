"""Task objects: an append-only event log, the current state it implies, brief associations,
and the inspector's open cases and latest evaluations."""

import sqlite3

VERSION = 30
DESCRIPTION = "Add task objects"

_TABLES = """
CREATE TABLE IF NOT EXISTS task_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    kind TEXT NOT NULL,
    actor TEXT NOT NULL,
    at REAL NOT NULL,
    request_id TEXT NOT NULL,
    data TEXT NOT NULL,
    UNIQUE (task_id, revision)
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    spec_brief_id TEXT NOT NULL,
    sponsor TEXT NOT NULL,
    subject_url TEXT NOT NULL,
    holder TEXT NOT NULL,
    previous_holder TEXT NOT NULL,
    checker_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    lifecycle TEXT NOT NULL CHECK (lifecycle IN ('open', 'check', 'closed')),
    assignment_event_id INTEGER NOT NULL,
    assigned_at REAL NOT NULL,
    attached_at REAL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_holder ON tasks(holder);
CREATE TABLE IF NOT EXISTS task_requests (
    request_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    result TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS brief_tasks (
    brief_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('holder', 'observer')),
    created_event_id INTEGER NOT NULL,
    PRIMARY KEY (brief_id, task_id)
);
CREATE INDEX IF NOT EXISTS idx_brief_tasks_task ON brief_tasks(task_id);
CREATE TABLE IF NOT EXISTS brief_task_exemptions (
    brief_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    checker_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    revision INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS task_dependencies (
    parent_task_id TEXT NOT NULL,
    child_task_id TEXT NOT NULL,
    created_event_id INTEGER NOT NULL,
    resolved_event_id INTEGER,
    CHECK (parent_task_id != child_task_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_dependencies_live
    ON task_dependencies(parent_task_id, child_task_id) WHERE resolved_event_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_task_dependencies_child ON task_dependencies(child_task_id);
CREATE TABLE IF NOT EXISTS task_cases (
    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    obligation TEXT NOT NULL,
    evidence TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('challenge', 'adjudicate')),
    target_kind TEXT NOT NULL,
    target TEXT NOT NULL,
    reason TEXT NOT NULL,
    basis TEXT NOT NULL,
    opened_at REAL NOT NULL,
    notified_at REAL,
    resolved_at REAL,
    notices INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_cases_open
    ON task_cases(subject, obligation, evidence) WHERE resolved_at IS NULL;
CREATE TABLE IF NOT EXISTS task_evaluations (
    subject TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    at REAL NOT NULL,
    outcome TEXT NOT NULL,
    detail TEXT NOT NULL,
    next_check TEXT NOT NULL
);
"""


def migrate(conn: sqlite3.Connection) -> None:
    for statement in _TABLES.split(";"):
        if statement.strip():
            conn.execute(statement)
