"""Queueing one `tell` message, and seeing that its recipient will read it.

A lemon that finished its work (its brief `done`, or its brief or inbox row
archived) is left alone unless the sender passed `--wake`. With `--wake`, any
recipient that won't read the message is brought back as `lemon resume
--recreate` would, with its transcript and directory checked first, instead of
by `tell`'s autoresume.
"""

import sqlite3
import typing as ty
from pathlib import Path

from .. import brief, lineage
from ..brief import archive
from ..config import load_config
from ..launch.restart import state
from ..log import get_logger
from ..openclaw import sessions
from ..watch import openclaw_scout, push_scout
from . import autoresume, bring_back, recipient, recreate, service, store, wake

_log = get_logger("messages.tell_delivery")


class Recipient(ty.NamedTuple):
    lemon_id: str
    attachment: brief.attached.Attachment | None  # None when archived or not started yet
    archived: bool  # its brief is in the attic
    parent: str  # its parent's Lemon-ID, or ""
    brief_path: Path | None


class Delivery(ty.NamedTuple):
    message: Path
    line: str  # for the sender, or ""
    will_read: bool
    unwakeable: bool  # nothing retried later would bring the recipient back
    state: str  # the recipient's, for the dead-letter log


def _recipient(
    conn: sqlite3.Connection, lemon_id: str, found: brief.attached.Attachment | None, archived: bool
) -> Recipient:
    return Recipient(
        lemon_id,
        found,
        archived,
        lineage.links.parent_of(conn, lemon_id) or "",
        found.path if found else brief.lemon.brief_of(conn, lemon_id),
    )


def resolve(conn: sqlite3.Connection, target: str) -> Recipient:
    """The lemon *target* names, attached or archived. Raises LookupError."""
    try:
        found = brief.lemon.attachment(conn, target)
        return _recipient(conn, brief.identity.ensure(conn, found.path), found, False)
    except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
        lemon_id = recreate.archived_id(conn, target)
        if not lemon_id:
            raise LookupError(str(error)) from error

        return _recipient(conn, lemon_id, None, True)


def by_id(conn: sqlite3.Connection, lemon_id: str) -> Recipient:
    """*lemon_id*'s lemon; one whose brief is neither attached nor archived hasn't started."""
    try:
        return resolve(conn, lemon_id)
    except LookupError:
        return _recipient(conn, lemon_id, None, False)


def _text(path: Path) -> str:
    try:
        return path.read_text()
    except OSError as error:
        _log.warning("Could not read brief %s: %s", path, error)
        return ""


def _woken(lemon_id: str, sender: str) -> tuple[str, bool, bool]:
    """(line for the sender, whether it will read the message, whether it is unwakeable)."""
    try:
        resumed = bring_back.resume(lemon_id, True, sender, wake.PROMPT, load_config())
    except bring_back.Refused as refused:
        then = (
            f"Nothing would bring it back; `lemonaid tell --wake-parent {lemon_id} <message>` "
            f"sends the message to the nearest lemon above {lemon_id} that can be woken."
            if refused.permanent
            else "Don't send it again; tell your user, your parent if you have one, or both."
        )
        return f"queued, but {str(refused).rstrip('.')}. {then}", False, refused.permanent

    return "; ".join(resumed.lines) + ". It reads the message once it is up.", True, False


def _pending_copy(to: Recipient, mailbox: Path, body: str, sender: str) -> Path | None:
    """A copy of *body* from *sender* still pending for *to*, here or, while its brief is
    archived, in the attic, where a refused wake put the copy it queued."""
    attic = archive.archived_mailboxes(to.lemon_id) if to.archived else []
    return next(
        (found for each in (mailbox, *attic) if (found := store.pending_copy(each, body, sender))),
        None,
    )


def deliver(to: Recipient, body: str, sender: str, wake_it: bool) -> Delivery:
    """Queue *body* for *to*, and start or prompt it as `tell` does. Raises ValueError."""
    mailbox = store.mailbox_for_id(to.lemon_id)
    path = (wake_it and _pending_copy(to, mailbox, body, sender)) or store.send(
        mailbox, body, sender
    )
    if to.archived:
        if wake_it:
            return Delivery(path, *_woken(to.lemon_id, sender), "archived")

        line = autoresume.finished_line(
            to.lemon_id, _text(to.brief_path) if to.brief_path else "", "archived", False
        )
        return Delivery(path, line, False, False, "archived")

    found = to.attachment
    channel, row = (found.channel, found.notification) if found else ("", None)
    if state.blocked(channel):
        return Delivery(path, f"queued for {to.lemon_id}: restart in progress", True, False, "")

    if channel.startswith("codex:"):
        service.ensure_running()
    elif channel.startswith("claude:") and row is not None:
        push_scout.ensure(channel.removeprefix("claude:"), to.lemon_id)
    elif channel.startswith(sessions.PREFIX) and row is not None:
        openclaw_scout.ensure(channel, to.lemon_id, str(row.metadata.get("cwd") or ""))
    found_state = recipient.probe(channel, row, mailbox)
    if found_state.state not in recipient.UNREAD:
        return Delivery(
            path, recipient.describe(to.lemon_id, found_state), True, False, found_state.state
        )

    if row is None or found is None:  # no record of its session to start
        line = autoresume.off(to.lemon_id, to.parent, found_state)
        return Delivery(path, line, False, False, found_state.state)

    if wake_it:
        return Delivery(path, *_woken(to.lemon_id, sender), found_state.state)

    text = _text(found.path)

    line, will_read = autoresume.respond(
        autoresume.Recipient(to.lemon_id, to.parent, row, text, mailbox),
        found_state,
        load_config(),
    )
    return Delivery(path, line, will_read, False, found_state.state)
