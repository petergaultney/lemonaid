"""Lemonaid's title for a Codex lemon, set as its thread's name, which the Codex app shows.

Codex keeps a thread's name in its store, and any app-server can set it there with
`thread/name/set`, whichever process has the thread loaded. A TUI saves the title it
generates only if the stored name is still the one it started with, so a name set before
it looks usually stays. One that loses that race, or a lemon renamed while idle, is set by
the next prompt or by the Codex service's next refresh, whichever comes first.
"""

from collections import abc

from ..inbox import db, session_title
from ..log import get_logger
from . import app_server, channels, stored

_log = get_logger("codex.thread_name")
_TIMEOUT = 5.0


def _answer(server: app_server.Server, method: str, params: dict) -> dict:
    [reply] = server.ask([(method, params)], _TIMEOUT)
    if "error" in reply:
        raise app_server.NoAnswer(str(reply["error"]))

    return reply["result"]


def _rename(server: app_server.Server, thread: str, name: str) -> bool:
    """Whether *thread* had another name and now has *name*."""
    record = _answer(server, "thread/read", {"threadId": thread, "includeTurns": False})
    if (record["thread"].get("name") or "").strip() == name:
        return False

    _answer(server, "thread/name/set", {"threadId": thread, "name": name})
    return True


def push(thread: str) -> None:
    """Give *thread* lemonaid's title for its lemon, unless Codex already has it. A thread
    with no inbox row, or whose lemon has neither an emoji nor a brief, keeps its name.

    Codex's name is read fresh rather than from the snapshot, which can still hold a name
    Codex has since replaced."""
    with db.connect() as conn:
        title = session_title.pending(conn, channels.channel(thread), "")
    if title and app_server.once(
        lambda server: _rename(server, thread, title), thread, False, _TIMEOUT
    ):
        _log.info("named thread %s: %r", thread, title)


def catch_up(server: app_server.Server, records: abc.Mapping[str, stored.Thread | None]) -> None:
    """Give each lemon's thread in *records*, just read from *server*, lemonaid's title where
    Codex holds another."""
    with db.connect() as conn:
        wanted = {
            thread: title
            for thread, record in records.items()
            if record is not None
            and not record.archived
            and (title := session_title.pending(conn, channels.channel(thread), record.name))
        }
    for thread, title in wanted.items():
        _answer(server, "thread/name/set", {"threadId": thread, "name": title})
        _log.info("named thread %s: %r", thread, title)
