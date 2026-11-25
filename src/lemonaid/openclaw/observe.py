"""`lemonaid openclaw observe`: keeps the inbox following OpenClaw's conversations.

Everything this learns it writes to the inbox database, where the grove, the inbox and `--self`
read it; none of them observe OpenClaw themselves. Another source of OpenClaw's events could
replace this module without changing those readers.
"""

import time
import typing as ty

from ..front_end import chat
from ..log import get_logger
from . import sessions, sync

_log = get_logger("openclaw.observe")

EVERY_SECONDS = 60.0


def _discover(cli: str, days: float) -> None:
    try:
        sync.refresh(cli, days, sync.CHATS, chat.NAME)
    except sessions.Unavailable as error:
        _log.warning("can't list OpenClaw sessions: %s", error)


def run(cli: str, days: float, every: float) -> ty.NoReturn:
    while True:
        try:
            _discover(cli, days)
        except Exception:  # the process's top: log it and try again next time
            _log.exception("OpenClaw discovery failed")
        time.sleep(every)
