"""Carrying out a rename asked for in the grove: a tree's tmux session, or a lemon's name."""

import functools
from collections import abc
from typing import Any

from ...inbox import db
from ..layout import edit, state
from ..tui.picking import Target


def _relayout(
    change: abc.Callable[[dict[str, Any], str, str, str], dict[str, Any]],
    groups: abc.Iterable[str],
    old: str,
    new: str,
) -> None:
    state.update(
        lambda before: functools.reduce(
            lambda saved, group: change(saved, group, old, new), groups, before
        )
    )


def _session(rename: Target, rename_session: abc.Callable[[str, str], str]) -> str:
    new = rename.name.replace(".", "_").replace(":", "_")  # as tmux would store it
    if not new:
        return "A session needs a name"
    if new == rename.tree:
        return ""
    _relayout(edit.share_tree, rename.groups, rename.tree, new)
    problem = rename_session(rename.tree, new)
    if problem:
        _relayout(edit.rename_tree, rename.groups, new, rename.tree)
        return problem

    with db.connect() as conn:
        for channel, window in rename.lemons:
            db.record_location(conn, channel, new, window)
    _relayout(edit.rename_tree, rename.groups, rename.tree, new)
    return f"renamed session {rename.tree} to {new}"


def _lemon(rename: Target) -> str:
    with db.connect() as conn:
        found = db.get_by_channel(conn, rename.channel, unread_only=False)
        if found is None:
            return f"No live lemon on {rename.channel}"

        db.update_name(conn, found.id, rename.name or None)
    return f"renamed {rename.name}" if rename.name else "name cleared"


def apply(rename: Target, rename_session: abc.Callable[[str, str], str] | None = None) -> str:
    """Carry out *rename*; what happened, for the prompt line. *rename_session(old, new)*
    renames a tmux session, saying why it couldn't or ""; without it, sessions aren't renamed.
    """
    if rename.channel:
        return _lemon(rename)
    if rename_session is None:
        return "renaming a session needs the grove popup or lma in tmux"

    return _session(rename, rename_session)
