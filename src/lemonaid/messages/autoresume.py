"""What `tell` does about a recipient that won't read the message: start it, or say why not.

A `done` or archived lemon finished its work, so it is left alone and the
sender is told how to resume it by hand.
"""

import sqlite3
import time
import typing as ty
from pathlib import Path

from ..brief import status
from ..config import Config
from ..inbox import db
from . import autoresume_cmux, autoresume_tmux, recipient, resume_log

START = "start"  # its harness exited: resume it in a new window
PROMPT = "prompt"  # its harness is idle with no waiter: type the wake prompt into it
FINISHED = "finished"  # done or archived: leave it alone
OFF = "off"  # autoresume isn't on for its harness
ASKING = "asking"  # stopped at a question for its user: typing would answer it

CHANNEL = "lemonaid:autoresume"


class Recipient(ty.NamedTuple):
    lemon_id: str
    parent: str  # its parent's Lemon-ID, or ""
    row: db.Notification
    brief_text: str
    inbox: Path


def plan(
    state: str, harness: str, brief_status: str, archived: bool, harnesses: frozenset[str]
) -> str:
    if brief_status == "done" or archived:
        return FINISHED

    if state == recipient.ASKING:
        return ASKING

    if harness not in harnesses:
        return OFF

    return START if state == recipient.DEAD else PROMPT


def _ask(parent: str) -> str:
    return f"ask its parent {parent} to resume it" if parent else "ask your user to resume it"


def _now_line(text: str) -> str:
    """The first line of `## Now` that isn't a sub-heading."""
    lines = (line.strip() for line in status.split(text).now.splitlines())
    return next(
        (line.removeprefix("- ") for line in lines if line and not line.startswith("#")), ""
    )


def finished(found: Recipient, state: recipient.State, config: Config) -> str:
    parts = status.split(found.brief_text)
    marked = "archived" if found.row.is_archived else f"marked {parts.status or 'done'}"
    running = "is not running and " if state.state == recipient.DEAD else ""
    command = autoresume_tmux.resume_line(found.row, config)
    return " ".join(
        [
            f"{found.lemon_id} {running}was {marked}",
            f"(Status: {parts.raw_status or 'none'}; Now: {_now_line(found.brief_text) or 'empty'}).",
            "The message is queued. If you want it to resume and continue,",
            f"run: {command}" if command else _ask(found.parent) + ".",
        ]
    )


def started(found: Recipient, action: str) -> str:
    snoozed = " It stays snoozed." if found.row.is_snoozed else ""
    if action == START:
        last = status.split(found.brief_text).status or "unknown"
        return (
            f"{found.lemon_id} was not running and its last status was {last}; "
            f"lemonaid started a resume for you, and it reads the message once it is up.{snoozed}"
        )

    return (
        f"{found.lemon_id} was idle with no inbox waiter; lemonaid prompted it to read "
        f"the message.{snoozed}"
    )


def failed(found: Recipient, state: recipient.State, why: str) -> str:
    return (
        f"queued, but {found.lemon_id} is {state.state} ({state.detail}) and lemonaid "
        f"could not start it: {why}. Don't send it again; tell your user, your parent "
        "if you have one, or both."
    )


def off(lemon_id: str, parent: str, state: recipient.State) -> str:
    return (
        f"queued, but {lemon_id} will not read it until it comes back: {state.state}, "
        f"{state.detail}. Don't send it again; {_ask(parent)}."
    )


def crash_looping(found: Recipient) -> str:
    """Tell the sender, and the user, that *found* won't be started again for now."""
    line = (
        f"queued, but {found.lemon_id} is crash-looping and not responding: lemonaid has "
        "started it too often recently and won't start it again yet. Don't send it again; "
        "tell your user, your parent if you have one, or both."
    )
    with db.connect() as conn:
        post(conn, f"ALERT: {found.lemon_id} is crash-looping; autoresume stopped starting it.")
    return line


def post(conn: sqlite3.Connection, line: str) -> None:
    """One line in the user's inbox, under the channel autoresume reports on."""
    db.add(conn, CHANNEL, line, name="autoresume")


def _bring_back(row: db.Notification, action: str, config: Config) -> str:
    """Start or prompt *row*'s lemon in the terminal it runs in. Returns why not, or ""."""
    terminal = row.switch_source or ("tmux" if row.metadata.get("tmux_session") else "")
    if terminal == "tmux":
        return (autoresume_tmux.start if action == START else autoresume_tmux.prompt)(row, config)

    if terminal == "cmux" and action == START:
        return autoresume_cmux.start(row, config)

    by_hand = autoresume_tmux.resume_line(row, config)
    return (
        f"lemonaid can't {'start' if action == START else 'prompt'} a lemon in "
        f"{terminal or 'this terminal'}"
        + (f"; it resumes with: {by_hand}" if action == START and by_hand else "")
    )


def respond(found: Recipient, state: recipient.State, config: Config) -> tuple[str, bool]:
    """What to tell the sender about a recipient in *state*, and whether it will now read the message."""
    action = plan(
        state.state,
        found.row.channel.partition(":")[0],
        status.split(found.brief_text).status,
        found.row.is_archived,
        config.messages.autoresume,
    )
    if action == FINISHED:
        return finished(found, state, config), False

    if action == OFF:
        return off(found.lemon_id, found.parent, state), False

    if action == ASKING:
        return (
            f"queued, but {found.lemon_id} stopped mid-turn to ask its user something and "
            "will read it after it is answered. Don't send it again; tell your user."
        ), False

    now, log = time.time(), resume_log.entries(found.inbox)
    if resume_log.starting(log, now):
        return (
            f"{found.lemon_id} is already being started, and reads the message once it is up.",
            True,
        )

    if state.state == recipient.DEAD and resume_log.died_quickly(log, now):
        resume_log.record(found.inbox, resume_log.FAILED)
        log = resume_log.entries(found.inbox)
    if (
        resume_log.within(log, now, config.messages.autoresume_window)
        >= config.messages.autoresume_max
    ):
        return crash_looping(found), False

    why = _bring_back(found.row, action, config)
    line = failed(found, state, why) if why else started(found, action)
    if not why:
        resume_log.record(found.inbox)
    with db.connect() as conn:
        if not why:
            db.hold_snooze_through_turns(conn, found.row.id)
        post(conn, line)
    return line, not why
