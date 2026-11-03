"""Facts for what a checker's `describe` declares it watches.

The kinds are task, lemon, lineage, pr, brief and file. Anything else is reported as a coverage
failure rather than ignored, since the checker would otherwise judge without data it
said it needs. A file is captured by content: its fact names a copy, keyed by its hash,
that a later edit to the file can't change.
"""

import hashlib
import shutil
import sqlite3
import typing as ty
from collections import abc
from pathlib import Path

from ... import brief, pr_url
from ...brief import status
from ...lemon_facts import facts
from ...watch import pr_activity
from ..checker import protocol
from ..checker.session import Ask
from ..model import holding, identities, ledger
from . import cases, lemon_watches, live

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


def _checks(snap: pr_activity.Snapshot) -> str:
    outcomes = {c.outcome for c in snap.checks}
    if not outcomes:
        return "none"

    if "pending" in outcomes:
        return "pending"

    return "failure" if "failed" in outcomes else "success"


def _pr(
    url: str, now: float, fetch: abc.Callable[[tuple[str, str]], pr_activity.Snapshot | None]
) -> list[live.Fact]:
    """`checks`, `draft`, `head` and `state` (OPEN, MERGED or CLOSED) for a PR."""
    key = pr_url.parse(url)
    snap = fetch(key) if key else None
    if snap is None:
        return [
            live.fact("pr", url, field, "", now, "unavailable")
            for field in ("checks", "draft", "head", "state")
        ]

    return [
        live.fact("pr", url, "checks", _checks(snap), now),
        live.fact("pr", url, "draft", str(snap.draft).lower(), now),
        live.fact("pr", url, "head", snap.head, now),
        live.fact("pr", url, "state", snap.state, now),
    ]


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


def _brief(conn: sqlite3.Connection, key: str, now: float) -> list[live.Fact]:
    try:
        path = brief.lemon.brief_of(conn, identities.current(conn, key) or key)
        text = path.read_text() if path else ""
    except (LookupError, ValueError, OSError):
        path, text = None, ""
    if path is None:
        return [
            live.fact("brief", key, field, "", now, "unavailable")
            for field in ("status", "needs", "waiting_on", "held")
        ]

    parts = status.split(text)
    said = brief.now.parse(parts.now)
    return [
        live.fact("brief", key, "status", parts.status, now),
        live.fact("brief", key, "needs", said.needs, now),
        live.fact("brief", key, "waiting_on", said.waiting_on, now),
        live.fact(
            "brief", key, "held", " ".join(t["task_id"] for t in holding.held_by(conn, key)), now
        ),
    ]


def _file(key: str, now: float) -> list[live.Fact]:
    try:
        content = Path(key).expanduser().read_bytes()
    except OSError:
        return [live.fact("file", key, "sha256", "", now, "unavailable")]

    digest = hashlib.sha256(content).hexdigest()
    captured = live.state_dir() / "task-captures" / digest
    if not captured.exists():
        captured.parent.mkdir(parents=True, exist_ok=True)
        temporary = captured.with_suffix(".tmp")
        temporary.write_bytes(content)
        shutil.move(temporary, captured)
    return [
        live.fact("file", key, "sha256", digest, now),
        live.fact("file", key, "captured", str(captured), now),
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
                found += _pr(key, now, pr)
            case "brief":
                found += _brief(conn, key, now)
            case "file":
                found += _file(key, now)
    return found
