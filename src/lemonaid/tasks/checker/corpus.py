"""A replay corpus: saved snapshots of tasks, cases and facts, as JSON, turned into checker input.

A corpus file is `{"snapshots": [...]}`. Each snapshot has a `name`, the evaluation time
`now`, optional `context` strings (policy settings among them), and lists of `tasks`,
`cases` and `facts`. A task or case is a flat object of string fields; a case names its
task in `task_id`. A fact has `kind`, `key`, `field`, `value`, `observed_at` and
`availability`. `expected` optionally maps task IDs to the verdict the snapshot should get.

Ownership or delivery the evidence doesn't show is recorded with availability `unknown`,
never guessed.
"""

import json
import typing as ty
from collections import abc
from pathlib import Path

from . import protocol

AVAILABILITY = frozenset({"known", "unknown", "unavailable"})

FACT_FIELDS = ("kind", "key", "field", "value", "observed_at", "availability")


class CorpusError(ValueError):
    pass


class Snapshot(ty.NamedTuple):
    name: str
    now: str
    context: dict[str, str]
    tasks: list[dict[str, str]]
    cases: list[dict[str, str]]
    facts: list[dict[str, str]]
    expected: dict[str, str]


class Input(ty.NamedTuple):
    snapshot: str
    task_id: str
    text: str


def _strings(raw: object, where: str) -> dict[str, str]:
    if not isinstance(raw, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in raw.items()
    ):
        raise CorpusError(f"{where}: expected an object of strings")

    return dict(raw)


def _fact(raw: object, where: str) -> dict[str, str]:
    fact = _strings(raw, where)
    if missing := [f for f in FACT_FIELDS if f not in fact]:
        raise CorpusError(f"{where}: missing {', '.join(missing)}")

    if fact["availability"] not in AVAILABILITY:
        raise CorpusError(f"{where}: availability {fact['availability']!r}")

    return fact


def _snapshot(raw: object, index: int) -> Snapshot:
    where = f"snapshot {index}"
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        raise CorpusError(f"{where}: needs a name")

    where = f"snapshot {raw['name']!r}"
    tasks = [_strings(t, f"{where} task {i}") for i, t in enumerate(raw.get("tasks", []))]
    if missing := [i for i, t in enumerate(tasks) if not t.get("task_id")]:
        raise CorpusError(f"{where}: tasks {missing} have no task_id")

    cases = [_strings(c, f"{where} case {i}") for i, c in enumerate(raw.get("cases", []))]
    if missing := [i for i, c in enumerate(cases) if not c.get("case_id") or not c.get("task_id")]:
        raise CorpusError(f"{where}: cases {missing} need case_id and task_id")

    return Snapshot(
        name=raw["name"],
        now=str(raw.get("now", "")),
        context=_strings(raw.get("context", {}), f"{where} context"),
        tasks=tasks,
        cases=cases,
        facts=[_fact(f, f"{where} fact {i}") for i, f in enumerate(raw.get("facts", []))],
        expected=_strings(raw.get("expected", {}), f"{where} expected"),
    )


def load(path: Path) -> list[Snapshot]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise CorpusError(f"{path}: {e}") from None

    if not isinstance(raw, dict) or not isinstance(raw.get("snapshots"), list):
        raise CorpusError(f"{path}: expected {{'snapshots': [...]}}")

    return [_snapshot(s, i) for i, s in enumerate(raw["snapshots"])]


def _records(snapshot: Snapshot, task: dict[str, str]) -> abc.Iterator[tuple[str, ...]]:
    context = {"now": snapshot.now, "snapshot": snapshot.name, **snapshot.context}
    yield from (("context", k, v) for k, v in context.items())
    yield from (("task", task["task_id"], k, v) for k, v in task.items() if k != "task_id")
    for case in snapshot.cases:
        if case["task_id"] == task["task_id"]:
            yield from (("case", case["case_id"], k, v) for k, v in case.items() if k != "case_id")
    yield from (tuple(["fact", *(f[name] for name in FACT_FIELDS)]) for f in snapshot.facts)


def inputs(snapshots: abc.Iterable[Snapshot]) -> abc.Iterator[Input]:
    """One evaluate input per task per snapshot; facts are shared by every task in a snapshot."""
    for snapshot in snapshots:
        for task in snapshot.tasks:
            yield Input(snapshot.name, task["task_id"], protocol.render(_records(snapshot, task)))
