"""Where waiters keep what they last reported to a lemon: its cursors.

A waiter compares the current state of what it watches with its cursor and reports what
differs, so a change made while no waiter ran is still reported by the next one. A
missing cursor means the lemon has just looked, so the waiter starts from the current state.

Cursors live under lemonaid's state directory, one directory per lemon, keyed by its
Lemon-ID (current through rerolls) so that every signature the lemon uses shares them.
A caller with no brief is keyed by its `--me` signature instead. Lemonaid passes its
state directory to the Codex lemons it starts as a writable root.
"""

import hashlib
import json
import os
import pathlib
import tempfile

from ..brief import lemon
from ..codex import channels
from ..inbox import db
from . import own_edits


def root() -> pathlib.Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return pathlib.Path(state).expanduser() / "cursors"


def owner(me: str, codex_thread: str = "") -> str:
    """The calling lemon's Lemon-ID; without a brief, a key for `me`, or else for its session."""
    try:
        with db.connect() as conn:
            return lemon.current(
                conn,
                lemon.own_id(
                    conn, channels.for_session(conn, codex_thread) if codex_thread else ""
                ),
            )
    except (LookupError, ValueError):
        pass
    if me:
        return f"me-{hashlib.sha1(me.encode()).hexdigest()[:12]}"

    return own_edits.writer_from_env(os.environ, codex_thread) or "anonymous"


def directory(kind: str, me: str, codex_thread: str = "") -> pathlib.Path:
    return root() / owner(me, codex_thread) / kind


def write_text(path: pathlib.Path, text: str) -> None:
    """Replace `path` whole, so a crash leaves the old cursor or the new one."""
    try:
        if path.read_text() == text:
            return

    except FileNotFoundError:
        pass

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)


def write_json(path: pathlib.Path, value: object) -> None:
    write_text(path, json.dumps(value))
