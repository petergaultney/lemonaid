"""Which lost lemons run in tmux now, told by their processes, for restore.

A row is pointed at the pane its lemon's own process runs in, and a lost lemon found
running is lost no longer, whether restore started it or someone resumed it by hand.
"""

import typing as ty
from collections import abc

from ..inbox import db, ended
from ..restore import run
from . import relink


def _place(location: abc.Mapping[str, ty.Any]) -> str:
    return f"{location.get('tmux_session')}:{location.get('tmux_window')}"


def running(lemons: abc.Sequence[run.Lemon]) -> set[str]:
    """The lemons whose own process runs in the window restore gave it, by process evidence
    rather than tty; their rows are pointed there and lose their lost mark."""
    wanted = {lemon.channel: lemon.spot.where for lemon in lemons}
    with db.connect() as conn:
        rows = [db.get_by_channel(conn, channel, unread_only=False) for channel in wanted]
        relinks = relink.survey(conn, [row for row in rows if row is not None]) or []
        there = [
            r
            for r in relinks
            if (r.state == relink.OK and _place(r.row.metadata) == wanted[r.row.channel])
            or (
                r.state == relink.RELINKED
                and r.location is not None
                and _place(r.location) == wanted[r.row.channel]
            )
        ]
        proven = [
            *(r for r in there if r.state == relink.OK),
            *relink.apply(conn, [r for r in there if r.state == relink.RELINKED]),
        ]
        for r in proven:
            db.clear_lost(conn, r.row.channel)
    return {r.row.channel for r in proven}


def _relinks(dry_run: bool) -> list[relink.Relink]:
    """Point every active row at the pane its lemon runs in: the ones restore started, the
    ones it left alone, and any whose old tty is now another lemon's."""
    with db.connect() as conn:
        relinks = relink.survey(conn) or []
        if dry_run:
            return [r for r in relinks if r.state in (relink.RELINKED, relink.FORGOTTEN)]

        applied = relink.apply(conn, relinks)
        found = [
            *(r for r in applied if r.state == relink.RELINKED),
            *(r for r in relinks if r.state == relink.OK),
        ]
        for r in found:
            if ended.revivable(r.row.metadata):
                db.clear_lost(conn, r.row.channel)
        return applied


def relinked(dry_run: bool) -> run.Relinked:
    relinks = _relinks(dry_run)
    return run.Relinked(relink.describe(relinks), relink.as_json(relinks))


def found(lost: abc.Sequence[db.Notification], dry_run: bool) -> set[str]:
    with db.connect() as conn:
        relinks = relink.survey(conn, lost) or []
    running_now = {r.row.channel for r in relinks if r.state in (relink.OK, relink.RELINKED)}
    if running_now and not dry_run:
        _relinks(dry_run=False)

    return running_now
