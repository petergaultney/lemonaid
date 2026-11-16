"""Resuming one lemon because someone asked to: `lemon resume` and `tell --wake`.

Unlike `tell`'s autoresume, this resumes a lemon marked done or archived, and
ignores `[messages] autoresume`: the caller has decided. It shares the start
limit, so a lemon that keeps dying is refused here too.

With *recreating* it also puts back what a toss took: the brief, the place's
directory and the tmux session (see `recreate`).
"""

import sqlite3
import time
import typing as ty
from pathlib import Path

from .. import brief
from ..brief import archive, archived_channel
from ..config import Config
from ..inbox import db, ended
from ..log import get_logger
from ..places import audit
from ..restore import auto, plan
from . import autoresume, autoresume_tmux, recipient, recreate, revive, store

_log = get_logger("messages.bring_back")
_TRANSCRIPT_GONE = (
    "its conversation's transcript is gone, so a resume would start an empty conversation "
    "under its name"
)
_NOTHING_TO_DO = frozenset({recipient.LISTENING, recipient.MID_TURN})


class Refused(Exception):
    """lemonaid won't resume the lemon. *permanent* when nothing retried later would change that."""

    def __init__(self, message: str, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


class Resumed(ty.NamedTuple):
    lemon_id: str
    lines: list[str]  # what was done, in order
    warning: str  # a Lemon-ID name clash, or ""


def _what_instead(row: db.Notification, brief_path: Path) -> str:
    transcript = str(row.metadata.get("transcript_path") or "")
    return (
        "A lemon resumed in another directory reads and edits the wrong files. If its branch "
        "still exists and it should keep working, recreate the directory (`lemonaid place "
        "acquire <key>`) and try again. If its work merged and you only have a question, read "
        f"its brief ({brief_path})"
        + (f" and transcript ({transcript})" if transcript else "")
        + ", or have a fresh lemon read them. If unsure, ask whoever started it"
    )


class Problem(ty.NamedTuple):
    why: str  # "" when there is none
    row: db.Notification | None  # the session's inbox row, when one is recorded
    directory: bool  # the problem is its directory


def unwakeable(
    conn: sqlite3.Connection, lemon_id: str, config: Config, events: list[dict]
) -> Problem:
    """Why the archived *lemon_id* could never come back, judged without changing anything.

    *events* are the places log's entries.
    """
    channel = archived_channel.of(conn, lemon_id)
    if not channel:
        return Problem("no session was recorded for it", None, False)

    row = db.get_by_channel(conn, channel, unread_only=False)
    if row is None:
        return Problem(f"its session {channel} has no inbox row", None, False)

    if plan.transcript_missing(row):
        return Problem(_TRANSCRIPT_GONE, row, False)

    if holder := recreate.holder(conn, channel):
        return Problem(
            f"its session {channel} has another brief attached now ({Path(holder).name})",
            row,
            False,
        )

    why = recreate.directory_problem(str(row.metadata.get("cwd") or ""), config, events)
    return Problem(why, row, bool(why))


def _refusal(lemon_id: str, problem: Problem, brief_path: Path, permanent: bool) -> Refused:
    advice = (
        _what_instead(problem.row, brief_path)
        if problem.directory and problem.row is not None
        else f"Its brief is {brief_path}"
    )
    return Refused(f"could not resume {lemon_id}: {problem.why}. {advice}", permanent)


def _found(
    target: str, recreating: bool, config: Config
) -> tuple[brief.attached.Attachment, str, bool]:
    """(attachment, Lemon-ID, whether its brief was revived from the attic for this)."""
    with db.connect() as conn:
        try:
            found = brief.lemon.attachment(conn, target)
            return found, brief.identity.ensure(conn, found.path), False
        except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
            lemon_id = recreate.archived_id(conn, target)
            if not lemon_id:
                raise Refused(str(error)) from error
            if not recreating:
                raise Refused(
                    f"{lemon_id}'s brief is archived. `lemonaid lemon resume {lemon_id} "
                    "--recreate` brings it back with the lemon"
                ) from error

        problem = unwakeable(conn, lemon_id, config, list(audit.entries(0)))
        if problem.why:
            brief_path = brief.lemon.brief_of(conn, lemon_id) or Path(lemon_id)
            raise _refusal(lemon_id, problem, brief_path, permanent=True)

        try:
            recreate.brief(conn, lemon_id)
            found = brief.lemon.attachment(conn, lemon_id)
        except (LookupError, ValueError) as error:  # no session recorded, or it is taken
            raise Refused(f"could not resume {lemon_id}: {error}", permanent=True) from error
        except (OSError, brief.store.ChangedUnderneath) as error:
            raise Refused(f"could not resume {lemon_id}: {error}") from error
    return found, lemon_id, True


def _back_to_attic(found: brief.attached.Attachment, lemon_id: str) -> None:
    """Undo `_found`'s revive after a refusal, so a refused wake changes nothing."""
    try:
        with db.connect() as conn:
            archive.archive(
                conn, found.path, time.time(), {found.channel}, why="resume of it was refused"
            )
    except (OSError, ValueError, sqlite3.Error) as error:
        _log.warning("Could not return %s's brief to the attic: %s", lemon_id, error)


def _recreated(lemon_id: str, row: db.Notification, brief_path: Path, config: Config) -> list[str]:
    cwd = str(row.metadata.get("cwd") or "")
    if why := recreate.directory_problem(cwd, config, audit.entries(0)):
        raise _refusal(lemon_id, Problem(why, row, True), brief_path, permanent=True)

    made_directory, why = recreate.directory(cwd, config)
    if why:  # its place's hooks failed, which a retry may not
        raise _refusal(lemon_id, Problem(why, row, True), brief_path, permanent=False)

    made_session, why = autoresume_tmux.recreate(row, cwd)
    if why:
        raise Refused(f"could not resume {lemon_id}: {why}")

    return [line for line in (made_directory, made_session) if line]


def _resume(
    found: brief.attached.Attachment,
    lemon_id: str,
    revived: bool,
    recreating: bool,
    who: str,
    text: str,
    config: Config,
) -> Resumed:
    done = (
        [f"revived {found.path.name} from the attic, attached to {found.channel}"]
        if revived
        else []
    )
    row = found.notification
    if row is None:
        raise Refused(
            f"{lemon_id} has no session recorded, so there is nothing to resume", permanent=True
        )

    if ended.revivable(row.metadata) and auto.running():
        raise Refused(
            f"{lemon_id} was lost with its terminal, and the restore running now will bring "
            "it back. Check on it once the restore has finished."
        )

    mailbox = store.mailbox_for_id(lemon_id)
    state = recipient.confirmed(row, recipient.probe(found.channel, row, mailbox))
    if state.state in _NOTHING_TO_DO:
        return Resumed(
            lemon_id,
            [*done, f"{lemon_id} is {state.state}: {state.detail}. Nothing to resume."],
            "",
        )

    if state.state not in (recipient.DEAD, recipient.DEAF):
        raise Refused(f"{lemon_id} is {state.state}: {state.detail}. lemonaid won't resume it.")

    dead = state.state == recipient.DEAD
    if dead and plan.transcript_missing(row):
        raise _refusal(lemon_id, Problem(_TRANSCRIPT_GONE, row, False), found.path, True)

    if dead and recreating:
        done.extend(_recreated(lemon_id, row, found.path, config))
    with db.connect() as conn:
        warning = brief.name_clash.warn(conn, lemon_id)
    outcome = revive.revive(row, mailbox, dead, config, text)
    if outcome.kind == revive.STARTING:
        return Resumed(lemon_id, [*done, f"{lemon_id} is already being started."], warning)

    if outcome.kind == revive.CRASH_LOOPING:
        raise Refused(
            f"{lemon_id} was started too often recently; lemonaid won't start it again yet."
        )

    with db.connect() as conn:
        if outcome.kind == revive.FAILED:
            autoresume.post(conn, f"{who} asked to resume {lemon_id}, but: {outcome.why}")
            raise Refused(f"could not resume {lemon_id}: {outcome.why}")

        line = (
            f"{who} resumed {lemon_id} in a new window"
            if dead
            else f"{who} prompted {lemon_id}, which was idle with no mailbox waiter"
        )
        autoresume.post(conn, line)
    return Resumed(lemon_id, [*done, line], warning)


def resume(target: str, recreating: bool, who: str, text: str, config: Config) -> Resumed:
    """Resume *target* if its harness exited, or prompt it on *text* if it is deaf.

    *who* asked, for the inbox line. Raises Refused.
    """
    found, lemon_id, revived = _found(target, recreating, config)
    try:
        return _resume(found, lemon_id, revived, recreating, who, text, config)
    except Refused:
        if revived:
            _back_to_attic(found, lemon_id)
        raise
