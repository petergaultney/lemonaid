"""`lemonaid openclaw observe`: keeps the inbox following OpenClaw's conversations, and the turns
running in them, from the gateway's events over a connection it keeps open.

Everything this learns it writes to the inbox database, where the grove, the inbox and `--self`
read it; none of them observe OpenClaw themselves. Another source of OpenClaw's events could
replace this module without changing those readers.
"""

import sqlite3
import threading
import time
import typing as ty

from ..config import load_config
from ..front_end import chat
from ..inbox import db
from ..log import get_logger
from . import gateway, sessions, sync, turn_end, turns

_log = get_logger("openclaw.observe")

EVERY_SECONDS = 60.0


def _discover(cli: str, days: float) -> None:
    try:
        sync.refresh(cli, days, sync.CHATS, chat.NAME)
    except sessions.Unavailable as error:
        _log.warning("can't list OpenClaw sessions: %s", error)


def _settle(session_key: str, cli: str, started: float) -> None:
    """Runs on a thread of its own: it asks the gateway, whose answer the connection's reader,
    which saw the turn end, would have to read."""
    try:
        failed = any(f.at_ms >= started * 1000 for f in turns.failed(session_key))
        turn_end.settle(session_key, cli, load_config().inbox.auto_read, started, failed)
    except sqlite3.Error:
        _log.exception("can't mark %s's finished turn", session_key)


def _recorder(cli: str) -> turns.Record:
    def record(session_key: str, at: float | None, started: float, ended: float) -> None:
        """Runs on the gateway connection's reader, which a raise would end."""
        try:
            with db.connect() as conn:
                db.record_turn_times(conn, sessions.channel(session_key), at, started, ended)
        except sqlite3.Error:
            _log.exception("can't record %s's turn", session_key)
        if at is None:
            threading.Thread(target=_settle, args=(session_key, cli, started), daemon=True).start()

    return record


def run(cli: str, days: float, every: float) -> ty.NoReturn:
    """A dropped connection is opened again within *every* seconds."""
    if not gateway.hold(_recorder(cli)):
        _log.warning("not following OpenClaw's turns: lemonaid lacks the `openclaw` extra")
    while True:
        try:
            gateway.listen()
        except Exception:  # the process's top: log it and try again next time
            _log.exception("can't hear OpenClaw's gateway")
        try:
            _discover(cli, days)
        except Exception:  # the process's top: log it and try again next time
            _log.exception("OpenClaw discovery failed")
        time.sleep(every)
