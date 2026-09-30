"""What a new lemon is handed: its brief, its parent, and its session's name.

Everything is checked before a window is touched, and the live channels are
taken then too, so a lemon that starts quickly still counts as new.
"""

import dataclasses
from pathlib import Path

from .. import brief, lineage
from ..inbox import db


@dataclasses.dataclass(frozen=True)
class Handoff:
    brief: Path | None = None
    live_before: tuple[str, ...] = ()
    link: tuple[str, str] | None = None  # (child, parent) Lemon-IDs
    name: str = ""


def prepare(brief_arg: str, parent: str, name: str) -> tuple[Handoff, str]:
    """The handoff the arguments ask for, and "" - or an empty one and the error."""
    path = brief.store.resolve(brief_arg) if brief_arg else None
    if path and (error := brief.store.outside_error(path)):
        return Handoff(), error

    if path and not path.is_file():
        return Handoff(), f"No brief at {path}"

    if parent and not path:
        return Handoff(), "--parent needs --brief: a link is between two Lemon-IDs"

    if name and not path:
        return Handoff(), "--name needs --brief: the name waits with it for the lemon to start"

    if not path:
        return Handoff(), ""

    with db.connect() as conn:
        live_before = tuple(brief.attached.live_channels(conn))
        if not parent:
            return Handoff(path, live_before, None, name), ""

        try:
            child = brief.identity.ensure(conn, path)
            parent_id = (
                brief.lemon.own_id(conn) if parent == "self" else brief.lemon.lemon_id(conn, parent)
            )
            lineage.links.check(conn, child, parent_id)
        except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
            return Handoff(), f"--parent {parent}: {error}"

    return Handoff(path, live_before, (child, parent_id), name), ""


def complete(handoff: Handoff, session: str, index: str, window_id: str) -> None:
    """Wait on the window for its lemon, and record the parent link now."""
    if handoff.brief is None:
        return

    with db.connect() as conn:
        brief.attached.attach_pending(
            conn, session, index, handoff.brief, handoff.live_before, window_id, handoff.name
        )
        if handoff.link:
            lineage.links.set_parent(conn, *handoff.link)
