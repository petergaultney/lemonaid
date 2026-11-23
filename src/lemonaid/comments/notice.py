"""An inbox row for each file a lemon has answered in, so a reply reaches the person even when
the editor isn't showing that file. One row per file and lemon, on its own channel, so it never
overwrites the lemon's own row; a later reply by that lemon in the same file updates it and adds
its id. The inbox draws the row under the lemon that wrote it. Activating the row opens the file
in the editor. The editor marks a row read once the person has seen every reply it lists, and it
learns which replies those are from the file's rows, so a reply written while the file was
closed is marked unread when it opens.
"""

import json
import pathlib
import sqlite3
import time
import typing as ty

from ..inbox import db
from . import model, parse

_PREFIX: ty.Final = "comments:"


def channel(path: pathlib.Path, lemon: str = "") -> str:
    """The row for the replies *lemon* (its channel) wrote in *path*, as `comments:<lemon>|<path>`:
    a lemon's channel has no `|` and a path starts with `/`, so no two rows share one. A row
    written before rows named their lemon is `comments:<path>`."""
    return f"{_PREFIX}{lemon}|{path.resolve()}" if lemon else f"{_PREFIX}{path.resolve()}"


def is_notice(n: db.Notification) -> bool:
    return n.channel.startswith(_PREFIX)


def lemon_of(n: db.Notification) -> str:
    """The channel of the lemon whose replies *n* lists, or "" for a row that names none."""
    lemon = (n.metadata or {}).get("lemon", "") if is_notice(n) else ""
    return lemon if isinstance(lemon, str) else ""


def _comments(n: db.Notification) -> list[str]:
    return [c for c in (n.metadata or {}).get("comments", []) if isinstance(c, str)]


def label(n: db.Notification) -> str:
    """The row's name in the inbox: the file, and how many of its replies are unread."""
    count = len(_comments(n)) if n.is_unread else 0
    return f"↳ 💬 {n.name or ''}" + (f" · {count} unread" if count else "")


def _unread_rows(conn: sqlite3.Connection, path: pathlib.Path) -> list[db.Notification]:
    """Every unread row for *path*, whichever lemon's replies it lists, by the path it stores."""
    rows = conn.execute(
        "SELECT * FROM notifications WHERE status = 'unread' AND substr(channel, 1, ?) = ?"
        " AND json_extract(metadata, '$.path') = ? ORDER BY created_at",
        (len(_PREFIX), _PREFIX, str(path.resolve())),
    )
    return [db.Notification.from_row(row) for row in rows]


def replied(path: pathlib.Path, author: str, comment_id: str, body: str, lemon: str = "") -> None:
    """*lemon*, the replying lemon's channel, places the row under that lemon in the inbox."""
    first_line = body.strip().splitlines()[0] if body.strip() else ""
    with db.connect() as conn:
        # read, merge and write as one transaction, so two writers never drop each other's id
        conn.execute("BEGIN IMMEDIATE")
        unread = db.get_by_channel(conn, channel(path, lemon))
        earlier = _comments(unread) if unread else []
        db.add(
            conn,
            channel(path, lemon),
            f"{author}: {first_line}",
            name=path.name,
            metadata={
                "path": str(path.resolve()),
                "comments": [*earlier, comment_id],
                "open_in_editor": str(path.resolve()),
                **({"lemon": lemon} if lemon else {}),
            },
        )


def unread_ids(path: pathlib.Path) -> list[str]:
    """The comments in `path` the person hasn't seen, by what its unread rows list."""
    with db.connect() as conn:
        return [c for row in _unread_rows(conn, path) for c in _comments(row)]


def seen(path: pathlib.Path, comment_ids: ty.Iterable[str]) -> None:
    """The person has seen `comment_ids`. Each row is marked read once it lists none they
    haven't, so a reply that came after the ones they saw keeps its row unread."""
    seen_ids = set(comment_ids)
    with db.connect() as conn:
        # Read and update every row as one transaction, so a reply posted meanwhile isn't
        # marked read; db's own helpers commit after each row, which would end it early.
        conn.execute("BEGIN IMMEDIATE")
        rows = _unread_rows(conn, path)
        _keep_only(conn, rows, {c for row in rows for c in _comments(row)} - seen_ids)
        conn.commit()


def _keep_only(conn: sqlite3.Connection, rows: list[db.Notification], kept: set[str]) -> None:
    """Each row lists only its comments in *kept*, and is marked read once it lists none."""
    for row in rows:
        listed = _comments(row)
        left = [c for c in listed if c in kept]
        if not left:
            conn.execute(
                "UPDATE notifications SET status = 'read', read_at = ? WHERE id = ?",
                (time.time(), row.id),
            )
        elif left != listed:
            conn.execute(
                "UPDATE notifications SET metadata = ? WHERE id = ?",
                (json.dumps(dict(row.metadata or {}) | {"comments": left}), row.id),
            )


def comment_ids(text: str, kind: model.FileKind) -> set[str] | None:
    """The comments *text* holds, or None when its threads can't be read whole, since a
    comment missing from a partial read may only be unreadable."""
    doc = parse.parse(text, kind)
    if any(e.kind in ("section", "record") for e in doc.errors):
        return None
    return {c.id for c in doc.comments}


def removed(path: pathlib.Path, held: set[str] | None, after: str, kind: model.FileKind) -> None:
    """Of the comments `path` *held*, those not in *after* were removed (stripped or
    deleted), so the person can't read them any more: drop them from its rows. Only those:
    a comment it never held (one written to another editor's unsaved buffer, or added
    since) keeps its row. When either can't be read whole, we drop nothing."""
    held_after = comment_ids(after, kind)
    if held is None or held_after is None:
        return
    if gone := held - held_after:
        seen(path, gone)
