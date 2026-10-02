"""A parent's children as a tree, with what each one's place is waiting on before cleanup.

Everything outside the database comes in as `child_place.World`, read once per command, so
a tree of any size asks tmux and the place hooks only once.
"""

import dataclasses
import sqlite3
from collections import abc

from ..inbox import status_since
from ..lineage import links
from . import attached, child_place, layout, lemon, pr_table, status


@dataclasses.dataclass(frozen=True)
class Child:
    lemon_id: str
    name: str  # its session's display name, or else its brief's title
    status: str  # "" when its brief is missing or has no known Status word
    since: float  # when lemonaid first saw the brief in this Status; 0 without a brief
    updated: float  # the brief's mtime; 0 without a brief
    brief: str
    channel: str  # "" until a lemon has claimed the brief
    tmux_session: str
    alive: bool | None  # whether tmux_session is live; None when tmux couldn't say
    clients: int | None  # clients attached to tmux_session
    place: child_place.Place | None
    prs: tuple[str, ...]  # the `### PRs` table's links
    children: tuple["Child", ...]
    held_by: tuple[str, ...]  # why its place can't be cleaned up yet; empty means ready
    cleanup: str  # "ready", "held", "orphan" (not done, session gone), or "cleaned"


def _prs(text: str) -> tuple[str, ...]:
    now = layout.parse(status.split(text).now)
    at = layout.find(now, "PRs")
    if at is None:
        return ()

    rows, _ = pr_table.parse(now.sections[at].body)
    return tuple(
        f"https://github.com/{repo}/pull/{number}"
        for row in rows
        if (found := pr_table.target(row.pr))
        for repo, number in [found]
    )


def _label(child: Child) -> str:
    return f"{child.name} ({child.lemon_id.rsplit('.', 1)[-1]})"


def _descendants(child: Child) -> abc.Iterator[Child]:
    for grandchild in child.children:
        yield grandchild
        yield from _descendants(grandchild)


def _orphaned(child: Child) -> bool:
    return child.status != "done" and child.alive is False


def _held_by(child: Child, world: child_place.World) -> tuple[str, ...]:
    family = [child, *_descendants(child)]
    sessions = dict.fromkeys(
        c.tmux_session for c in family if c.tmux_session and c.alive is not False
    )
    own = f"status {child.status or 'unknown'}"
    return (
        *([] if child.status == "done" else [f"session gone, {own}" if _orphaned(child) else own]),
        *(f"{_label(c)} is {c.status or 'unknown'}" for c in family[1:] if c.status != "done"),
        *(
            ["tmux didn't say who is attached"]
            if sessions and world.clients is None
            else [
                f"a client is attached to {s}"
                for s in sessions
                if world.clients and world.clients.get(s)
            ]
        ),
    )


def _child(
    conn: sqlite3.Connection,
    lemon_id: str,
    world: child_place.World,
    by_path: abc.Mapping[str, attached.Attachment],
    seen: frozenset[str],
) -> Child:
    path = lemon.brief_of(conn, lemon_id)
    text = path.read_text() if path and path.is_file() else ""
    parts = status.split(text)
    mtime = path.stat().st_mtime if text and path else 0.0
    since = status_since.observe(conn, {path: (parts.status, mtime)}) if text and path else {}
    found = by_path.get(str(path)) if path else None
    notification = found.notification if found else None
    session = found.tmux_session if found else ""
    below = tuple(
        _child(conn, grandchild, world, by_path, seen | {lemon_id})
        for grandchild in links.children_of(conn, lemon_id)
        if grandchild not in seen
    )
    child = Child(
        lemon_id=lemon_id,
        name=(notification.name if notification and notification.name else "") or parts.title,
        status=parts.status,
        since=since.get(path, 0.0) if path else 0.0,
        updated=mtime,
        brief=str(path or ""),
        channel=found.channel if found else "",
        tmux_session=session,
        alive=(session in world.sessions) if session and world.sessions is not None else None,
        clients=world.clients.get(session, 0) if session and world.clients is not None else None,
        place=child_place.of(
            notification.metadata.get("cwd", "") if notification else "", session, world
        ),
        prs=_prs(text),
        children=below,
        held_by=(),
        cleanup="",
    )
    held_by = _held_by(child, world)
    return dataclasses.replace(
        child,
        held_by=held_by,
        cleanup=(
            "orphan"
            if _orphaned(child)
            else "held"
            if held_by
            else "cleaned"
            if child.alive is False and child.place and not child.place.exists
            else "ready"
        ),
    )


def shown(child: Child, everything: bool) -> bool:
    """Whether a list leaves *child* in: anything but done with its directory known to be gone."""
    return everything or child.status != "done" or not child.place or child.place.exists


def of(conn: sqlite3.Connection, parent_id: str, world: child_place.World) -> list[Child]:
    """*parent_id*'s children, each with its own children nested under it."""
    attached.claim_pending(conn)
    by_path = {str(a.path): a for a in attached.everything(conn)}
    return [
        _child(conn, lemon_id, world, by_path, frozenset({parent_id}))
        for lemon_id in links.children_of(conn, parent_id)
    ]
