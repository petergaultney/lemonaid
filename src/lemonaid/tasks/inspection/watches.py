"""Facts for what a checker's `describe` declares it watches.

The kinds are task, lemon, lineage, pr, brief and file. Anything else is reported as a coverage
failure rather than ignored, since the checker would otherwise judge without data it
said it needs.
"""

import sqlite3
import typing as ty
from collections import abc

from ...lemon_facts import facts
from ..checker import protocol
from ..checker.session import Ask
from ..model import identities, ledger
from . import brief_facts, cases, lemon_watches, live, pr_facts

KINDS = frozenset({"task", "lemon", "lineage", "pr", "brief", "file"})


class Unsupported(ValueError):
    pass


def declared(ask: Ask, text: str) -> list[tuple[str, str]]:
    """The (kind, key) watches the checker declares for the subject in *text*. Raises
    ProtocolError or Unsupported, or what *ask* raises."""
    records = protocol.parse(ask("describe", text), protocol.DESCRIBE)
    found = [(r[1], r[2]) for r in records]
    if unknown := sorted({kind for kind, _ in found} - KINDS):
        raise Unsupported(f"the checker watches {', '.join(unknown)}, which lemonaid can't observe")

    return found


def _task(conn: sqlite3.Connection, key: str, now: float) -> list[live.Fact]:
    state = ledger.state(conn, key)
    if state is None:
        return [live.fact("task", key, "lifecycle", "", now, "unavailable")]

    finding = cases.finding(conn, key)
    judged = finding in ("ok", "wait", "challenge", "adjudicate")
    return [
        live.fact("task", key, "lifecycle", state["lifecycle"], now),
        live.fact("task", key, "holder", state["holder"], now),
        live.fact(
            "task", key, "finding", finding if judged else "", now, "known" if judged else "unknown"
        ),
    ]


def facts_for(
    conn: sqlite3.Connection,
    watches: abc.Iterable[tuple[str, str]],
    seen: ty.Mapping[str, facts.Facts],
    pr: abc.Callable[[tuple[str, str]], ty.Any],
    now: float,
) -> list[live.Fact]:
    found: list[live.Fact] = []
    for kind, key in dict.fromkeys(watches):
        match kind:
            case "task":
                found += _task(conn, key, now)
            case "lemon":
                found += lemon_watches.lemon(
                    key, seen.get(identities.current(conn, key) or key), now
                )
            case "lineage":
                found += lemon_watches.lineage(conn, key, seen, now)
            case "pr":
                found += pr_facts.facts(key, now, pr)
            case "brief":
                found += brief_facts.facts(conn, key, now, live.vaults())
            case "file":
                found += brief_facts.file(key, now)
    return found
