"""The inspector's open cases and each subject's latest evaluation.

A subject is `task:<id>`, or `brief:<id>` for the missing-task coverage pass. A complete
finding set replaces the subject's cases: a re-emitted challenge stays open (and isn't
sent again), and an omitted one is resolved. A failed or unknown evaluation leaves every
case as it was, but a task case is about one assignment and subject URL (its basis), so
closing, reassigning or re-pointing the task resolves it whatever the checker says. An
evaluation older than the subject's latest is dropped. These run inside a caller's
`ledger.transaction`.
"""

import json
import sqlite3
import typing as ty
from collections import abc

from ..checker import protocol

ACCUSATIONS = frozenset({"challenge", "adjudicate"})

_RANK = ("challenge", "adjudicate", "unknown", "wait", "ok")


def outcome(records: abc.Iterable[protocol.Record]) -> str:
    """The strongest finding in a set: a set with any challenge is a challenge."""
    kinds = {r[0] for r in records}
    return next((kind for kind in _RANK if kind in kinds), "ok")


def _next_check(records: abc.Iterable[protocol.Record]) -> str:
    times = [r[2] for r in records if r[0] == "recheck"] + [r[5] for r in records if r[0] == "wait"]
    return min(times, default="")


def _evaluated(
    conn: sqlite3.Connection,
    subject: str,
    revision: int,
    at: float,
    result: str,
    detail: str,
    next_check: str,
) -> None:
    conn.execute(
        "INSERT INTO task_evaluations (subject, revision, at, outcome, detail, next_check)"
        " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (subject) DO UPDATE SET"
        " revision = excluded.revision, at = excluded.at, outcome = excluded.outcome,"
        " detail = excluded.detail, next_check = excluded.next_check",
        (subject, revision, at, result, detail, next_check),
    )


_BASIS = (
    "t.assignment_event_id || '|' || t.subject_url || CASE WHEN t.lifecycle = 'closed'"
    " THEN '|closed:' || (SELECT MAX(e.event_id) FROM task_events e"
    " WHERE e.task_id = t.task_id AND e.kind = 'closed') ELSE '' END"
)


def basis(conn: sqlite3.Connection, task_id: str) -> str:
    """What a task's cases are about: its current assignment and subject URL, and for a
    closed task, the closing, so reopening or closing it again drops cases about another."""
    return conn.execute(f"SELECT {_BASIS} FROM tasks t WHERE t.task_id = ?", (task_id,)).fetchone()[
        0
    ]


def superseded(conn: sqlite3.Connection, at: float) -> int:
    """Resolve open task cases whose basis moved on; returns how many."""
    return conn.execute(
        "UPDATE task_cases SET resolved_at = ? WHERE resolved_at IS NULL"
        " AND subject LIKE 'task:%' AND NOT EXISTS (SELECT 1 FROM tasks t"
        f" WHERE 'task:' || t.task_id = task_cases.subject AND {_BASIS} = task_cases.basis)",
        (at,),
    ).rowcount


def newer(conn: sqlite3.Connection, subject: str, at: float) -> bool:
    """Whether *subject* already has an evaluation from after *at*."""
    row = conn.execute("SELECT at FROM task_evaluations WHERE subject = ?", (subject,)).fetchone()
    return bool(row) and row["at"] > at


def _sent_before(conn: sqlite3.Connection, case: tuple[str, ...]) -> tuple[int, float | None]:
    """The notices of the latest resolved case with the same accusation to the same target,
    so a case reopened on the same facts keeps when its message was last sent. *case* is
    (subject, obligation, evidence, target_kind, target, basis)."""
    row = conn.execute(
        "SELECT notices, notified_at FROM task_cases WHERE subject = ? AND obligation = ?"
        " AND evidence = ? AND target_kind = ? AND target = ? AND basis = ?"
        " AND resolved_at IS NOT NULL ORDER BY case_id DESC LIMIT 1",
        case,
    ).fetchone()
    return (row["notices"], row["notified_at"]) if row else (0, None)


def apply(
    conn: sqlite3.Connection,
    subject: str,
    revision: int,
    records: abc.Sequence[protocol.Record],
    at: float,
    case_basis: str,
) -> list[dict[str, ty.Any]]:
    """Record a checker's finding set for *subject*, computed from inputs taken at *at*;
    returns the cases it newly opened. An `unknown` set is recorded but changes no case."""
    result = outcome(records)
    _evaluated(conn, subject, revision, at, result, json.dumps(records), _next_check(records))
    if result == "unknown":
        return []

    found = {(r[2], r[3]): r for r in records if r[0] in ACCUSATIONS}
    open_now = {
        (row["obligation"], row["evidence"]): row["case_id"]
        for row in conn.execute(
            "SELECT case_id, obligation, evidence FROM task_cases"
            " WHERE subject = ? AND resolved_at IS NULL",
            (subject,),
        )
    }
    for key, case_id in open_now.items():
        if key not in found:
            conn.execute("UPDATE task_cases SET resolved_at = ? WHERE case_id = ?", (at, case_id))

    opened = []
    for (obligation, evidence), record in found.items():
        if (obligation, evidence) in open_now:
            continue

        kind, _, _, _, target_kind, target, reason = record
        sent = _sent_before(conn, (subject, obligation, evidence, target_kind, target, case_basis))
        conn.execute(
            "INSERT INTO task_cases (subject, obligation, evidence, kind, target_kind, target,"
            " reason, basis, opened_at, notices, notified_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                subject,
                obligation,
                evidence,
                kind,
                target_kind,
                target,
                reason,
                case_basis,
                at,
                *sent,
            ),
        )
        opened.append({"subject": subject, "obligation": obligation, "target": target})
    return opened


def failed(conn: sqlite3.Connection, subject: str, revision: int, reason: str, at: float) -> None:
    """Record a checker failure; the subject's cases stay as they were."""
    _evaluated(conn, subject, revision, at, "failure", reason, "")


def open_cases(conn: sqlite3.Connection) -> list[dict[str, ty.Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM task_cases WHERE resolved_at IS NULL ORDER BY opened_at, case_id"
        )
    ]


def resolve(conn: sqlite3.Connection, case_id: int, at: float) -> None:
    conn.execute("UPDATE task_cases SET resolved_at = ? WHERE case_id = ?", (at, case_id))


def is_open(conn: sqlite3.Connection, case_id: int) -> bool:
    row = conn.execute(
        "SELECT resolved_at FROM task_cases WHERE case_id = ?", (case_id,)
    ).fetchone()
    return bool(row) and row["resolved_at"] is None


def notified(conn: sqlite3.Connection, case_id: int, at: float) -> None:
    conn.execute(
        "UPDATE task_cases SET notified_at = ?, notices = notices + 1 WHERE case_id = ?",
        (at, case_id),
    )


def finding(conn: sqlite3.Connection, task_id: str) -> str:
    """The latest evaluation's outcome for *task_id*, or "" if it was never evaluated."""
    row = conn.execute(
        "SELECT outcome FROM task_evaluations WHERE subject = ?", (f"task:{task_id}",)
    ).fetchone()
    return row["outcome"] if row else ""


def evaluations(conn: sqlite3.Connection) -> list[dict[str, ty.Any]]:
    return [dict(row) for row in conn.execute("SELECT * FROM task_evaluations ORDER BY subject")]
