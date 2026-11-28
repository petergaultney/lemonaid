"""`lemonaid openclaw observe`: keeps the inbox following OpenClaw's conversations, and the turns
running in them, from the gateway's events over a connection it keeps open.

Everything this learns it writes to the inbox database, where the grove, the inbox and `--self`
read it; none of them observe OpenClaw themselves. Another source of OpenClaw's events could
replace this module without changing those readers.
"""

import json
import sqlite3
import subprocess
import sys
import threading
import time
import typing as ty

from ..config import load_config
from ..conversation import openclaw as conversation
from ..front_end import chat
from ..inbox import db
from ..log import get_logger
from . import gateway, sessions, sync, turns

_log = get_logger("openclaw.observe")

EVERY_SECONDS = 60.0
_SETTLE_SECONDS = 60.0


def _discover(cli: str, days: float) -> None:
    try:
        sync.refresh(cli, days, sync.CHATS, chat.NAME)
    except sessions.Unavailable as error:
        _log.warning("can't list OpenClaw sessions: %s", error)


def _settle(session_key: str, cli: str, started: float) -> None:
    """Runs on a thread of its own: it asks the gateway, whose answer the connection's reader,
    which saw the turn end, would have to read. The rest runs in `openclaw hook turn-end`,
    whose main thread the rule check's regex time limit needs."""
    failed = any(f.at_ms >= started * 1000 for f in turns.failed(session_key))
    config = load_config()
    said = ""
    if (config.inbox.auto_read or config.rules.patterns) and not failed:
        try:
            said = conversation.final_message(session_key, cli, started)
        except OSError as error:
            _log.warning("can't read %s's final message: %s", session_key, error)
    payload = {"session_key": session_key, "said": said, "failed": failed}
    try:
        done = subprocess.run(
            [sys.executable, "-m", "lemonaid", "openclaw", "hook", "turn-end"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=_SETTLE_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        _log.warning("can't settle %s's finished turn: %s", session_key, error)
        return

    if done.returncode != 0:
        _log.warning("settling %s's finished turn exited %d", session_key, done.returncode)


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
