"""Sending the inspector's challenges to the briefs they name, with backoff.

A case is checked again just before it is sent, so a task closed, reassigned or given a
disposition since its evaluation sends nothing. A case still open is sent again after
the interval, then twice it, four times... up to the ceiling; one about a closed task is
sent once. A case reopened with the
same accusation against the same assignment, to the same recipient, keeps its place in that backoff.
"""

import sqlite3
import typing as ty
from collections import abc

from ...messages import store
from ..briefs import registration
from ..model import identities, ledger
from . import cases


def _covered(conn: sqlite3.Connection, case: ty.Mapping[str, ty.Any]) -> bool:
    """Whether a missing-task case's brief has a disposition now."""
    subject = case["subject"]
    return subject.startswith("brief:") and bool(
        registration.disposition(conn, subject.removeprefix("brief:"))
    )


def _body(case: ty.Mapping[str, ty.Any]) -> str:
    return (
        f"The task inspector, about {case['subject']} ({case['obligation']}):\n\n{case['reason']}"
    )


def _about_closed_task(conn: sqlite3.Connection, case: ty.Mapping[str, ty.Any]) -> bool:
    """Nobody holds a closed task to keep answering, so its case is sent once."""
    kind, _, task_id = case["subject"].partition(":")
    row = conn.execute("SELECT lifecycle FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    return kind == "task" and row is not None and row["lifecycle"] == "closed"


def _due(case: ty.Mapping[str, ty.Any], interval: float, ceiling: float, now: float) -> bool:
    last = case["notified_at"]
    return last is None or now >= last + min(ceiling, interval * 2 ** (max(case["notices"], 1) - 1))


def deliver(
    conn: sqlite3.Connection,
    interval: float,
    ceiling: float,
    opted_out: abc.Collection[str],
    now: float,
) -> list[str]:
    """Message each open challenge to a brief that is due, unless the brief is in
    *opted_out*; returns a line per message. With no *interval*, the lines say what would
    be sent. Adjudications and other targets are reported, not sent."""
    lines = []
    for case in cases.open_cases(conn):
        with ledger.transaction(conn):
            cases.superseded(conn, now)  # the task may have moved on since its evaluation
            if _covered(conn, case):
                cases.resolve(conn, case["case_id"], now)
            still = cases.is_open(conn, case["case_id"])
        target = case["target"]
        if (
            not still
            or not _due(case, interval, ceiling, now)
            or (case["notices"] and _about_closed_task(conn, case))
            or case["kind"] != "challenge"
            or case["target_kind"] != "brief"
            or any(name in opted_out for name in identities.names(conn, target))
        ):
            continue

        if not interval:
            lines.append(f"would tell {target} about {case['subject']} ({case['obligation']})")
            continue

        try:
            store.send(store.inbox_for_id(target), _body(case), "lemonaid task inspector")
        except (ValueError, OSError) as error:
            lines.append(f"telling {target} about {case['subject']} failed: {error}")
            continue

        with ledger.transaction(conn):
            cases.notified(conn, case["case_id"], now)
        lines.append(f"told {target} about {case['subject']} ({case['obligation']})")
    return lines
