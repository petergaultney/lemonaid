"""An inbox row for each file a lemon has answered in, so a reply reaches the person even when
the editor isn't showing that file. One row per file, on its own channel, so it never
overwrites the lemon's own row; a later reply in the same file updates it and adds its id.
Activating the row opens the file in the editor. The editor marks the row read once the
person has seen every reply there, and it learns which replies those are from the row, so
a reply written while the file was closed is marked unread when it opens.
"""

import pathlib
import typing as ty

from ..inbox import db

_PREFIX: ty.Final = "comments:"


def channel(path: pathlib.Path) -> str:
    return f"{_PREFIX}{path.resolve()}"


def replied(path: pathlib.Path, author: str, comment_id: str, body: str) -> None:
    first_line = body.strip().splitlines()[0] if body.strip() else ""
    with db.connect() as conn:
        # read, merge and write as one transaction, so two writers never drop each other's id
        conn.execute("BEGIN IMMEDIATE")
        unread = db.get_by_channel(conn, channel(path))
        earlier = (unread.metadata or {}).get("comments", []) if unread else []
        db.add(
            conn,
            channel(path),
            f"{author} in {path.name}: {first_line}",
            name=path.name,
            metadata={
                "path": str(path.resolve()),
                "comments": [*earlier, comment_id],
                "open_in_editor": str(path.resolve()),
            },
        )


def unread_ids(path: pathlib.Path) -> list[str]:
    """The comments in `path` the person hasn't seen, by what its unread row lists."""
    with db.connect() as conn:
        unread = db.get_by_channel(conn, channel(path))
    comments = (unread.metadata or {}).get("comments", []) if unread else []
    return [c for c in comments if isinstance(c, str)]


def seen(path: pathlib.Path, comment_ids: ty.Iterable[str]) -> None:
    """The person has seen `comment_ids`. The row is marked read once it lists none it
    hasn't, so a reply that came after the ones they saw keeps it unread."""
    with db.connect() as conn:
        # read and update as one transaction, so a reply posted meanwhile isn't marked read
        conn.execute("BEGIN IMMEDIATE")
        if (unread := db.get_by_channel(conn, channel(path))) is None:
            conn.rollback()
            return
        metadata = dict(unread.metadata or {})
        seen_ids = set(comment_ids)
        left = [c for c in metadata.get("comments", []) if c not in seen_ids]
        if left:
            db.update_metadata(conn, unread.id, metadata | {"comments": left})
        else:
            db.mark_read(conn, unread.id)
