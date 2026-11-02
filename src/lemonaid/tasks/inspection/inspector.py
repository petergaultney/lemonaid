"""One inspector pass: evaluate every open task with the checker, check that every working
brief has a task, and keep the open cases those findings imply.

A lemon taking a turn may be about to change its status or hand its task on, so a task
whose holder is mid-turn, like a brief that is, waits for a later pass; its cases stand.

A finding applies only to the task revision it was computed for; one that a concurrent
change superseded is dropped, and the next pass evaluates the new revision.
"""

import sqlite3
import subprocess
import typing as ty
from collections import abc

from ...lemon_facts import facts
from ...messages import recipient
from ..checker import corpus, protocol, replay
from ..checker.session import Ask
from ..model import dependencies, identities, ledger
from . import cases, coverage, live, memory, task_input, watches

_IDLE_GRACE = 120  # the default policy's default, for released dependencies


class Observers(ty.NamedTuple):
    """Where a pass reads the live world; tests replace these."""

    lemons: abc.Callable[[sqlite3.Connection], dict[str, facts.Facts]]
    pr: abc.Callable[[tuple[str, str]], ty.Any]


LIVE = Observers(live.lemons, live.fetch_pr)


class Pass(ty.NamedTuple):
    evaluated: int
    opened: list[dict[str, ty.Any]]
    failures: list[tuple[str, str]]  # subject, why


def _input(
    conn: sqlite3.Connection,
    state: ty.Mapping[str, ty.Any],
    now: float,
    context: ty.Mapping[str, str],
    seen: ty.Mapping[str, facts.Facts],
    observers: Observers,
    ask: Ask,
    remembered: memory.Memory,
) -> corpus.Input:
    """The task's evaluate input, with the facts its checker declares it watches and the
    task's own release and cycle facts. Raises what `watches.declared` raises."""
    grace = float(context.get("policy.idle_grace", _IDLE_GRACE))
    releases = task_input.released(conn, state, now, grace)
    task = task_input.fields(conn, state, releases)
    [bare] = corpus.inputs([task_input.snapshot(now, context, task, [], [])])
    found = [
        *watches.facts_for(
            conn,
            memory.watches(remembered, task["task_id"], bare.text, ask, watches.declared),
            seen,
            observers.pr,
            now,
        ),
        *task_input.dependency_facts(
            state["task_id"], releases, dependencies.loop_through(conn, state["task_id"]), now
        ),
    ]
    open_cases = task_input.case_records(conn, f"task:{state['task_id']}")
    [one] = corpus.inputs([task_input.snapshot(now, context, task, found, open_cases)])
    return one


def _evaluate(
    conn: sqlite3.Connection,
    state: ty.Mapping[str, ty.Any],
    build: abc.Callable[[], corpus.Input],
    ask: Ask,
    remembered: memory.Memory,
    now: float,
) -> tuple[list[dict[str, ty.Any]], str]:
    """(cases opened, failure) for one task; both empty when a newer revision or a newer
    pass superseded this one, or when nothing the checker was shown has changed since it
    last judged the task and its findings still hold."""
    task_id, revision = state["task_id"], state["revision"]
    try:
        one = build()
        if memory.unchanged(remembered, task_id, one.text, now):
            return [], ""

        records = protocol.parse(ask("evaluate", one.text), protocol.EVALUATE)
        replay.check_findings(task_id, records)
        memory.remember(remembered, task_id, one.text, records)
        failure = ""
    except (
        protocol.ProtocolError,
        watches.Unsupported,
        subprocess.SubprocessError,
        OSError,
    ) as error:
        records, failure = [], str(error) or type(error).__name__
        memory.forget(remembered, task_id)

    subject = f"task:{task_id}"
    with ledger.transaction(conn):
        current = ledger.state(conn, task_id)
        if current is None or current["revision"] != revision or cases.newer(conn, subject, now):
            return [], ""

        if failure:
            cases.failed(conn, subject, revision, failure, now)
            return [], failure

        return cases.apply(conn, subject, revision, records, now, cases.basis(conn, task_id)), ""


def _mid_turn(conn: sqlite3.Connection, holder: str, seen: ty.Mapping[str, facts.Facts]) -> bool:
    if not holder.startswith("brief:"):
        return False

    name = holder.removeprefix("brief:")
    found = seen.get(identities.current(conn, name) or name)
    return found is not None and found.state == recipient.MID_TURN


# A closing is judged until a pass reaches a verdict on it, and again while it has an open
# case; one still inconclusive a day after it closed, such as a PR no lemon watches, is left.
_CLOSED_UNCHECKED = (
    "SELECT t.* FROM tasks t LEFT JOIN task_evaluations e ON e.subject = 'task:' || t.task_id"
    " WHERE t.lifecycle = 'closed' AND (e.revision IS NULL OR e.revision < t.revision"
    " OR EXISTS (SELECT 1 FROM task_cases c WHERE c.subject = e.subject AND c.resolved_at IS NULL)"
    " OR (e.outcome IN ('unknown', 'failure') AND (SELECT MAX(at) FROM task_events"
    " WHERE task_id = t.task_id AND kind = 'closed') > ?))"
)

_CLOSING_RECHECK = 86400.0


def run(
    conn: sqlite3.Connection,
    now: float,
    ask: Ask,
    policy: ty.Mapping[str, str],
    observers: Observers = LIVE,
    remembered: memory.Memory | None = None,
) -> Pass:
    """One pass. A *remembered* memory, kept across passes, skips what hasn't changed; with
    none, every subject is judged."""
    remembered = remembered if remembered is not None else memory.new()
    with ledger.transaction(conn):
        cases.superseded(conn, now)
    seen = observers.lemons(conn)
    context = {f"policy.{k}": v for k, v in policy.items()}
    states = [
        *(
            dict(r)
            for r in conn.execute("SELECT * FROM tasks WHERE lifecycle != 'closed'")
            if not _mid_turn(conn, r["holder"], seen)
        ),
        *(dict(r) for r in conn.execute(_CLOSED_UNCHECKED, (now - _CLOSING_RECHECK,))),
    ]
    opened, failures = [], []
    for state in states:
        found, failure = _evaluate(
            conn,
            state,
            lambda s=state: _input(conn, s, now, context, seen, observers, ask, remembered),
            ask,
            remembered,
            now,
        )
        opened += found
        if failure:
            failures.append((f"task:{state['task_id']}", failure))
    covered, uncovered = coverage.check(conn, seen, observers.pr, now, context, ask, remembered)
    return Pass(len(states), [*opened, *covered], [*failures, *uncovered])
