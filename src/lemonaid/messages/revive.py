"""Bring back a lemon that won't read its inbox, in the terminal it ran in, at most so often.

A dead lemon is resumed in a new window; an idle one with no waiter has the
prompt typed into it. Both `tell`'s autoresume and `lemon resume` start
lemons through here, so both count against the same limit.
"""

import time
import typing as ty
from pathlib import Path

from ..config import Config
from ..inbox import db
from . import autoresume_cmux, autoresume_tmux, resume_log

STARTED = "started"
STARTING = "starting"  # a start in the last minute may still be coming up
CRASH_LOOPING = "crash-looping"  # started too often recently
FAILED = "failed"


class Outcome(ty.NamedTuple):
    kind: str
    why: str = ""  # for FAILED


def bring_back(row: db.Notification, start: bool, config: Config, text: str) -> str:
    """Resume (*start*) or prompt *row*'s lemon on *text*. Returns why not, or ""."""
    terminal = row.switch_source or ("tmux" if row.metadata.get("tmux_session") else "")
    if terminal == "tmux":
        return (autoresume_tmux.start if start else autoresume_tmux.prompt)(row, config, text)

    if terminal == "cmux" and start:
        return autoresume_cmux.start(row, config, text)

    by_hand = autoresume_tmux.resume_line(row, config)
    return (
        f"lemonaid can't {'start' if start else 'prompt'} a lemon in "
        f"{terminal or 'this terminal'}"
        + (f"; it resumes with: {by_hand}" if start and by_hand else "")
    )


def revive(row: db.Notification, inbox: Path, dead: bool, config: Config, text: str) -> Outcome:
    """Resume *row*'s lemon if *dead*, else prompt it, unless the start log says not to.

    A lemon found dead soon after its last start counts that start as failed.
    """
    now, log = time.time(), resume_log.entries(inbox)
    if resume_log.starting(log, now):
        return Outcome(STARTING)

    if dead and resume_log.died_quickly(log, now):
        resume_log.record(inbox, resume_log.FAILED)
        log = resume_log.entries(inbox)
    if resume_log.within(log, now, config.messages.autoresume_window) >= (
        config.messages.autoresume_max
    ):
        return Outcome(CRASH_LOOPING)

    if why := bring_back(row, dead, config, text):
        return Outcome(FAILED, why)

    resume_log.record(inbox)
    with db.connect() as conn:
        db.hold_snooze_through_turns(conn, row.id)
    return Outcome(STARTED)
