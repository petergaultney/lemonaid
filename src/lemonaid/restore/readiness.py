"""Knowing before a crash which running lemons would not come back from it.

Checked on the inbox watcher's schedule, and listed in one inbox row,
`lemonaid:restore-readiness`, which goes away once nothing is missing. Each front end
that restores lemons says what it lacks for a lemon, and which running lemons the inbox
has no row for; nothing adopts those unattended, since only a person can confirm which
conversation runs there.
"""

import sqlite3
from collections import abc

from .. import resume
from ..config import Config
from ..inbox import db, ended
from . import front_ends, plan, run

CHANNEL = "lemonaid:restore-readiness"


def _why(row: db.Notification, terminal: run.Terminal, config: Config) -> str:
    if why := terminal.unready(row):
        return why

    if resume.build_resume_command(config, row.channel, row.metadata) is None:
        return "no way to resume it"

    if plan.transcript_missing(row):
        return "its transcript is gone"

    return ""


def unready(
    rows: abc.Iterable[db.Notification], config: Config
) -> list[tuple[db.Notification, str]]:
    """Each running lemon that its front end could not bring back, and why."""
    groups, _ = front_ends.groups((row for row in rows if not ended.cause(row.metadata)), False)
    return [
        (row, why)
        for group in groups
        for row in group.rows
        if (why := _why(row, group.terminal, config))
    ]


def check(conn: sqlite3.Connection, config: Config) -> None:
    """List what restore couldn't bring back: unready rows, and lemons with no row."""
    terminals = front_ends.restorers()
    missing = [
        *(f"{row.name or row.channel}: {why}" for row, why in unready(db.get_active(conn), config)),
        *(stray for terminal in terminals for stray in terminal.strays()),
    ]
    if not missing:
        db.archive_channel(
            conn, CHANNEL, "every lemon is ready", cause=ended.ARCHIVED, by="restore"
        )
        return

    message = " ".join(
        [
            f"{len(missing)} running lemons would not come back if their terminal died: "
            + "; ".join(missing)
            + ".",
            *(terminal.advice for terminal in terminals),
        ]
    )
    existing = db.get_by_channel(conn, CHANNEL, unread_only=False)
    if existing is None or existing.is_archived or existing.message != message:
        db.add(conn, CHANNEL, message, name="restore readiness", status="read")
