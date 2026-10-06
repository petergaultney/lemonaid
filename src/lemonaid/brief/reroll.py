"""Give a lemon a new WordyBin, carrying over everything recorded against its old Lemon-ID.

The old ID stays an alias of the new one, and its inbox folder is left holding
only a forward, so a message addressed to it still reaches the lemon.
"""

import dataclasses
import os
import re
import sqlite3
from pathlib import Path

import wordybin

from .. import home, messages
from . import identity, store

_ATTEMPTS = 20
_LINE = re.compile(r"^(?:Brief-ID|Lemon-ID): .*$", re.MULTILINE)


@dataclasses.dataclass(frozen=True)
class Rerolled:
    old_id: str
    new_id: str


def _word(chosen: str) -> str:
    """*chosen* spelled as WordyBin spells two bytes; raises ValueError otherwise."""
    decoded = wordybin.decode(chosen)
    if len(decoded) != 2:
        raise ValueError(f"{chosen!r} is not a two-word WordyBin")

    return wordybin.encode(decoded)


def _taken(conn: sqlite3.Connection, lemon_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM lemon_identities WHERE lemon_id = ?"
        " UNION SELECT 1 FROM lemon_aliases WHERE old_id = ?",
        (lemon_id, lemon_id),
    ).fetchone()
    return row is not None or messages.store.inbox_for_id(lemon_id).exists()


def _new_id(conn: sqlite3.Connection, path: Path, old_id: str, chosen: str) -> str:
    slug = old_id.rsplit(".", 1)[0] if "." in old_id else store.lemon_id_slug(path)
    if chosen:
        new_id = f"{slug}.{_word(chosen)}"
        if new_id == old_id:
            raise ValueError(f"{old_id} already has that WordyBin")

        if _taken(conn, new_id):
            raise ValueError(f"{new_id} is, or was, another lemon's Lemon-ID")

        return new_id

    for _ in range(_ATTEMPTS):
        new_id = f"{slug}.{wordybin.encode(os.urandom(2))}"
        if new_id != old_id and not _taken(conn, new_id):
            return new_id

    raise ValueError(f"No free WordyBin for {slug} after {_ATTEMPTS} tries")


def _with_id(text: str, old_id: str, new_id: str) -> str:
    if identity.read(text) != old_id:
        raise store.ChangedUnderneath("The brief's Lemon-ID changed during the reroll")

    return _LINE.sub(f"Brief-ID: {new_id}", text, count=1)


def _relabel(conn: sqlite3.Connection, path: Path, old_id: str, new_id: str) -> None:
    conn.execute("UPDATE lemon_identities SET lemon_id = ? WHERE path = ?", (new_id, str(path)))
    conn.execute("UPDATE lemon_parents SET lemon_id = ? WHERE lemon_id = ?", (new_id, old_id))
    conn.execute("UPDATE lemon_parents SET parent_id = ? WHERE parent_id = ?", (new_id, old_id))
    conn.execute("UPDATE lemon_aliases SET lemon_id = ? WHERE lemon_id = ?", (new_id, old_id))
    conn.execute("INSERT INTO lemon_aliases (old_id, lemon_id) VALUES (?, ?)", (old_id, new_id))


def _move_inbox(old_id: str, new_id: str) -> None:
    """One rename carries pending messages, done/, and the lock files together."""
    old, new = messages.store.inbox_for_id(old_id), messages.store.inbox_for_id(new_id)
    if old.is_dir():
        old.rename(new)
    else:
        new.mkdir(parents=True)
    old.mkdir()
    (old / messages.store.FORWARD).write_text(new_id + "\n")


def _unmove_inbox(old_id: str, new_id: str) -> None:
    """Undo as much of `_move_inbox` as it got through."""
    old, new = messages.store.inbox_for_id(old_id), messages.store.inbox_for_id(new_id)
    if not new.is_dir():
        return

    (old / messages.store.FORWARD).unlink(missing_ok=True)
    if old.is_dir():
        old.rmdir()
    new.rename(old)


def reroll(conn: sqlite3.Connection, path: Path, chosen: str = "") -> Rerolled:
    """Give the brief at *path* a new WordyBin: *chosen*, or a random unused one.

    Every brief and message write waits for this, so a message sent while it
    runs lands either before the move or behind the forward.
    """
    with home.guard.exclusive():
        old_id = identity.ensure(conn, path)
        path = path.resolve()
        conn.execute("BEGIN IMMEDIATE")
        moved = rewritten = False
        try:
            new_id = _new_id(conn, path, old_id, chosen)
            _relabel(conn, path, old_id, new_id)
            moved = True
            _move_inbox(old_id, new_id)
            store.edit(path, lambda text: _with_id(text, old_id, new_id))
            rewritten = True
            conn.commit()
        except BaseException:
            conn.rollback()
            if rewritten:
                store.edit(path, lambda text: _with_id(text, new_id, old_id))
            if moved:
                _unmove_inbox(old_id, new_id)
            raise

    return Rerolled(old_id, new_id)
