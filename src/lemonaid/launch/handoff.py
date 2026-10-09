"""What a new lemon is handed: its brief, its parent, its groups, and its session's name.

A lemon with a parent and no `--group` goes into its parent's groups.

Everything is checked before a window is touched, and the live channels are
taken then too, so a lemon that starts quickly still counts as new.
"""

import dataclasses
from pathlib import Path

from .. import brief, groups, lineage
from ..inbox import db
from ..log import get_logger

_log = get_logger("launch.handoff")


@dataclasses.dataclass(frozen=True)
class Handoff:
    brief: Path | None = None
    live_before: tuple[str, ...] = ()
    link: tuple[str, str] | None = None  # (child, parent) Lemon-IDs
    name: str = ""
    lemon_id: str = ""  # the --brief lemon's, when a parent or a group needs it
    groups: tuple[str, ...] = ()


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
            parent_id = (
                brief.lemon.own_id(conn) if parent == "self" else brief.lemon.lemon_id(conn, parent)
            )
            lineage.links.check(conn, child, parent_id)
        except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
            return Handoff(), f"--parent {parent}: {error}"

        # A child joins its parent's groups unless it was given its own.
        found = found or groups.store.names_of(conn, parent_id)

    return Handoff(path, live_before, (child, parent_id), name, child, found), ""


def complete(handoff: Handoff, session: str, index: str, window_id: str) -> None:
    """Wait on the window for its lemon, and record the parent link and groups now."""
    if handoff.brief is None:
        return

    with db.connect() as conn:
        brief.attached.attach_pending(
            conn, session, index, handoff.brief, handoff.live_before, window_id, handoff.name
        )
        if handoff.link:
            lineage.links.set_parent(conn, *handoff.link)
        for group in handoff.groups:
            try:
                groups.store.add(conn, groups.store.find(conn, group), [handoff.lemon_id])
            except LookupError as error:
                _log.warning("Not adding %s to a group: %s", handoff.lemon_id, error)
        if handoff.groups:
            groups.sync.write_lines(conn, [handoff.lemon_id])
