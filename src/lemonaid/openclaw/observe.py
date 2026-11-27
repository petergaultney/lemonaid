"""`lemonaid openclaw observe`: keeps the inbox following OpenClaw's conversations, and the turns
running in them, from the gateway's events over a connection it keeps open.

Everything this learns it writes to the inbox database, where the grove, the inbox and `--self`
read it; none of them observe OpenClaw themselves. Another source of OpenClaw's events could
replace this module without changing those readers.
"""

import sqlite3
import time
import typing as ty

from ..front_end import chat
from ..inbox import db
from ..log import get_logger
from . import gateway, sessions, sync

_log = get_logger("openclaw.observe")

EVERY_SECONDS = 60.0


def _discover(cli: str, days: float) -> None:
    try:
        sync.refresh(cli, days, sync.CHATS, chat.NAME)
    except sessions.Unavailable as error:
        _log.warning("can't list OpenClaw sessions: %s", error)


def _record_turn(session_key: str, at: float | None, started: float, ended: float) -> None:
    """Runs on the gateway connection's reader, which a raise would end."""
    try:
        with db.connect() as conn:
            db.record_turn_times(conn, sessions.channel(session_key), at, started, ended)
    except sqlite3.Error:
        _log.exception("can't record %s's turn", session_key)


def run(cli: str, days: float, every: float) -> ty.NoReturn:
    """A dropped connection is opened again within *every* seconds."""
    if not gateway.hold(_record_turn):
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
