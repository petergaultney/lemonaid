"""The changes an edit begun in the grove makes, once it knows what it needs: the inbox's own
edits, applied to every lemon an edit's target covers. No dialogs here, so the grove window can
make them too.
"""

from ... import brief, groups
from ...inbox import db, pins
from ...inbox.tui.edits import inbox_edits
from .. import grafts
from ..tui.picking import Target


def channels_of(target: Target) -> list[str]:
    return [target.channel] if target.channel else [channel for channel, _ in target.lemons]


def _live(conn, target: Target) -> list[db.Notification]:
    found = (db.get_by_channel(conn, channel, unread_only=False) for channel in channels_of(target))
    return [n for n in found if n is not None]


def _counted(verb: str, done: int, after: str = "") -> str:
    if not done:
        return "no live lemon to change"
    return f"{verb} {done} lemon{'' if done == 1 else 's'}{after}"


def archive(target: Target) -> str:
    with db.connect() as conn:
        found = _live(conn, target)
    return _counted("archived", sum(inbox_edits.archive(n.id) is not None for n in found))


def snooze(target: Target, until: float) -> str:
    with db.connect() as conn:
        found = _live(conn, target)
    for n in found:
        inbox_edits.snooze(n, until)
    return _counted("snoozed", len(found))


def pin(target: Target) -> str:
    """Pin them all, unless all are pinned already: then unpin them."""
    with db.connect() as conn:
        channels = channels_of(target)
        pinning = not all(pins.is_pinned(conn, channel) for channel in channels)
        for channel in channels:
            (pins.pin if pinning else pins.unpin)(conn, channel)
    return _counted("pinned" if pinning else "unpinned", len(channels))


def _lemon_id(conn, channel: str) -> str:
    """The ID a group knows a lemon by: its brief's Lemon-ID, else its channel."""
    try:
        return brief.lemon.lemon_id(conn, channel)
    except (LookupError, ValueError, brief.store.ChangedUnderneath):
        return channel


def _members(conn, name: str) -> tuple[str, ...]:
    try:
        return groups.store.find(conn, name).members
    except LookupError:
        return ()


def move(target: Target, name: str) -> str:
    moved = 0
    try:
        with db.connect() as conn:
            for channel in channels_of(target):
                lemon_id = _lemon_id(conn, channel)
                if lemon_id not in _members(conn, name):
                    groups.editing.add(conn, name, lemon_id, channel)
                if target.block not in ("", name) and lemon_id in _members(conn, target.block):
                    groups.editing.remove(
                        conn, groups.store.find(conn, target.block), lemon_id, channel
                    )
                moved += 1
    except groups.store.GroupError as error:
        return str(error)
    return _counted("moved", moved, f' to "{name}"')


def graft(target: Target, onto: str) -> str:
    """Graft each lemon onto the tree of the lemon on channel *onto*, or with "" put each back
    on its own tree."""
    with db.connect() as conn:
        lemons = {channel: _lemon_id(conn, channel) for channel in channels_of(target)}
        if not onto:
            ungrafted = sum(bool(grafts.ungraft(conn, pair)) for pair in lemons.items())
            return _counted("ungrafted", ungrafted) if ungrafted else "no graft to undo"

        host = _lemon_id(conn, onto)
        try:
            for lemon in lemons.values():
                grafts.graft(conn, lemon, host)
        except grafts.GraftError as error:
            return str(error)
    return _counted("grafted", len(lemons), f" onto {brief.identity.brief_name(host) or host}")


def group_names(target: Target) -> list[str]:
    with db.connect() as conn:
        return [
            g.name for g in groups.store.all_groups(conn) if g.members and g.name != target.block
        ]


def recolor(target: Target, wanted: str) -> str:
    try:
        with db.connect() as conn:
            groups.editing.recolor(conn, groups.store.find(conn, target.block), wanted)
    except (LookupError, groups.store.GroupError) as error:
        return str(error)
    return f'recolored "{target.block}"'


def saved_color(target: Target) -> str:
    with db.connect() as conn:
        return groups.store.find(conn, target.block).saved_color
