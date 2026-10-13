"""What a new lemon is handed: its brief, its parent, its groups, and its session's name.

A lemon with a parent and no `--group` goes into its parent's groups.
`--parent parent` names the caller's own parent, or no one if it has none.
A parent other than the caller is told, in its inbox, that it has a new child.

Everything is checked before a window is touched, and the live channels are
taken then too, so a lemon that starts quickly still counts as new.
"""

import dataclasses
import re
from pathlib import Path

from .. import brief, groups, lineage
from ..inbox import db
from ..log import get_logger
from ..messages import store as inbox_store

_log = get_logger("launch.handoff")


@dataclasses.dataclass(frozen=True)
class Handoff:
    brief: Path | None = None
    live_before: tuple[str, ...] = ()
    link: tuple[str, str] | None = None  # (child, parent) Lemon-IDs
    name: str = ""
    lemon_id: str = ""  # the --brief lemon's, when a parent or a group needs it
    groups: tuple[str, ...] = ()
    announce: str = ""  # the caller's Lemon-ID, when the parent is someone else


_TRAILING_BRIEF = re.compile(r"[\s:\-]*\bbrief\W*$", re.IGNORECASE)


def session_title(given: Handoff) -> str:
    """The title for the lemon's harness session: its --name, else its brief's
    first heading without a trailing "brief"."""
    if given.name or not given.brief:
        return given.name

    for line in given.brief.read_text().splitlines():
        if line.startswith("# "):
            return _TRAILING_BRIEF.sub("", line[2:].strip())

    return ""


def first_prompt(given: Handoff, prompt: str) -> str:
    """*prompt*, or the default that sends a new lemon to its task file.

    It leads with the title because Codex titles a session from its first prompt.
    """
    if prompt or not given.brief:
        return prompt

    task = f"Your task file is {given.brief}; read it all and do the work."
    return f"{title}. {task}" if (title := session_title(given)) else task


def prepare(
    brief_arg: str, parent: str, name: str, group_names: tuple[str, ...] = ()
) -> tuple[Handoff, str]:
    """The handoff the arguments ask for, and "" - or an empty one and the error."""
    path = brief.store.resolve(brief_arg) if brief_arg else None
    if path and (error := brief.store.outside_error(path)):
        return Handoff(), error

    if path and not path.is_file():
        return Handoff(), f"No brief at {path}"

    if parent and not path:
        return Handoff(), "--parent needs --brief: a link is between two Lemon-IDs"

    if group_names and not path:
        return Handoff(), "--group needs --brief: a group holds Lemon-IDs"

    if name and not path:
        return Handoff(), "--name needs --brief: the name waits with it for the lemon to start"

    if not path:
        return Handoff(), ""

    with db.connect() as conn:
        live_before = tuple(brief.attached.live_channels(conn))
        if not parent and not group_names:
            return Handoff(path, live_before, None, name), ""

        try:
            child = brief.identity.ensure(conn, path)
        except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
            return Handoff(), f"--brief {brief_arg}: {error}"

        try:
            found = tuple(groups.store.find(conn, group).name for group in group_names)
        except (LookupError, groups.store.GroupError) as error:
            return Handoff(), f"--group: {error}"

        if not parent:
            return Handoff(path, live_before, None, name, child, found), ""

        try:
            caller = brief.lemon.own_id(conn)
        except (LookupError, ValueError, brief.store.ChangedUnderneath):
            caller = ""

        try:
            if parent == "parent":
                parent_id = lineage.links.parent_of(conn, caller) if caller else ""
            elif parent == "self":
                parent_id = brief.lemon.own_id(conn)
            else:
                parent_id = brief.lemon.lemon_id(conn, parent)
            if parent_id:
                lineage.links.check(conn, child, parent_id)
        except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
            return Handoff(), f"--parent {parent}: {error}"

        if not parent_id:  # `--parent parent` from a lemon with no parent
            return Handoff(path, live_before, None, name, child, found), ""

        # A child joins its parent's groups unless it was given its own.
        found = found or groups.store.names_of(conn, parent_id)

    announce = "" if parent_id == caller else (caller or "someone")
    return Handoff(path, live_before, (child, parent_id), name, child, found, announce), ""


def _announce(handoff: Handoff) -> None:
    child, parent = handoff.link or ("", "")
    try:
        inbox_store.send(
            inbox_store.inbox_for_id(parent),
            f"{handoff.announce} started {handoff.name or child} as your child ({handoff.brief})",
            handoff.announce,
        )
    except (ValueError, OSError) as error:
        _log.warning("Could not tell %s about its new child %s: %s", parent, child, error)


def complete(handoff: Handoff, session: str, index: str, window_id: str) -> str:
    """Wait on the window for its lemon, and record the parent link and groups now.

    Returns a warning for the caller to show when the lemon's name is another's too.
    """
    if handoff.brief is None:
        return ""

    with db.connect() as conn:
        brief.attached.attach_pending(
            conn, session, index, handoff.brief, handoff.live_before, window_id, handoff.name
        )
        if handoff.link:
            lineage.links.set_parent(conn, *handoff.link)
            if handoff.announce:
                _announce(handoff)
        for group in handoff.groups:
            try:
                groups.store.add(conn, groups.store.find(conn, group), [handoff.lemon_id])
            except LookupError as error:
                _log.warning("Not adding %s to a group: %s", handoff.lemon_id, error)
        if handoff.groups:
            groups.sync.write_lines(conn, [handoff.lemon_id])
        try:
            lemon_id = handoff.lemon_id or brief.identity.ensure(conn, handoff.brief)
        except (ValueError, brief.store.ChangedUnderneath) as error:
            _log.warning("Not checking %s for a shared name: %s", handoff.brief, error)
            return ""

        return brief.name_clash.warn(conn, lemon_id)
