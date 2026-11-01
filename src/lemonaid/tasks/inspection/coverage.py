"""The inspector's coverage check: lemonaid finds the working briefs with no task
disposition, and the checker judges each as a `brief` subject, as it judges a task.

A brief that has a disposition is covered without asking the checker, which resolves any
case still open for it. A brief subject's `parent` is its nearest ancestor that has a
disposition of its own, since one without can't be relied on to define a task.
"""

import sqlite3
import subprocess
import typing as ty
from collections import abc

from ...lemon_facts import facts
from ...lineage import links
from ...messages import recipient
from ..briefs import registration
from ..checker import corpus, protocol, replay
from ..model import ledger
from . import cases, live, task_input, watches


def _text(
    now: float,
    context: ty.Mapping[str, str],
    lemon_id: str,
    parent: str,
    found: abc.Iterable[ty.Mapping[str, str]],
    open_cases: abc.Iterable[ty.Mapping[str, str]],
) -> str:
    return protocol.render(
        [
            *(("context", k, v) for k, v in {"now": live.stamp(now), **context}.items()),
            ("brief", lemon_id, "parent", parent),
            *(
                ("case", c["case_id"], k, v)
                for c in open_cases
                for k, v in c.items()
                if k != "case_id"
            ),
            *(("fact", *(f[name] for name in corpus.FACT_FIELDS)) for f in found),
        ]
    )


def _helper(conn: sqlite3.Connection, lemon_id: str) -> str:
    """The nearest ancestor of *lemon_id* that has a task disposition of its own, which
    can define a task for it; "" when none does."""
    seen = {lemon_id}
    parent = links.parent_of(conn, lemon_id)
    while parent and parent not in seen:
        if registration.disposition(conn, parent):
            return parent

        seen.add(parent)
        parent = links.parent_of(conn, parent)
    return ""


def _judge(
    conn: sqlite3.Connection,
    lemon_id: str,
    seen: ty.Mapping[str, facts.Facts],
    pr: abc.Callable[[tuple[str, str]], ty.Any],
    now: float,
    context: ty.Mapping[str, str],
    argv: abc.Sequence[str],
    timeout: float,
) -> list[protocol.Record]:
    """The checker's findings for *lemon_id*'s brief. Raises what the checker's run raises."""
    parent = _helper(conn, lemon_id)
    declared = watches.declared(argv, _text(now, context, lemon_id, parent, [], []), timeout)
    found = watches.facts_for(conn, declared, seen, pr, now)
    open_cases = task_input.case_records(conn, f"brief:{lemon_id}")
    text = _text(now, context, lemon_id, parent, found, open_cases)
    records = protocol.parse(replay.run_checker(argv, text, timeout), protocol.EVALUATE)
    replay.check_findings(lemon_id, records)
    return records


def check(
    conn: sqlite3.Connection,
    seen: ty.Mapping[str, facts.Facts],
    pr: abc.Callable[[tuple[str, str]], ty.Any],
    now: float,
    context: ty.Mapping[str, str],
    argv: abc.Sequence[str],
    timeout: float,
) -> tuple[list[dict[str, ty.Any]], list[tuple[str, str]]]:
    """The cases opened for briefs with no task, and the briefs the checker failed on."""
    opened, failures = [], []
    for lemon_id, found in seen.items():
        if found.state == recipient.MID_TURN:
            continue

        subject = f"brief:{lemon_id}"
        records: list[protocol.Record] = [("ok", lemon_id, "covered")]
        if not registration.disposition(conn, lemon_id):
            try:
                records = _judge(conn, lemon_id, seen, pr, now, context, argv, timeout)
            except (
                protocol.ProtocolError,
                watches.Unsupported,
                subprocess.SubprocessError,
                OSError,
            ) as error:
                with ledger.transaction(conn):
                    cases.failed(conn, subject, 0, str(error) or type(error).__name__, now)
                failures.append((subject, str(error) or type(error).__name__))
                continue

        with ledger.transaction(conn):
            opened += cases.apply(conn, subject, 0, records, now, "")
    return opened, failures
