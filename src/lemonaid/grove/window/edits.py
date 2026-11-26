"""The terminal grove's select-mode edits, from the window's right-click menu: rename, snooze,
archive, pin, move to another group or onto another lemon's tree, and recolor, made by the same
changes. A block's menu also changes block numbers: home (block 0) and earlier or later.
"""

import dataclasses
import time
from collections import abc

from ...config import Config
from ...inbox import snooze_time
from ..source import block_numbers, changes, renames
from ..tui import keys, picking
from ..tui.frame import Grove

ACTIONS = ("rename", "snooze", "archive", "pin", "group", "graft", "color")


def _target(grove: Grove, action: str, digit: str, key: str, channel: str) -> picking.Target | str:
    """What *action* changes: block *digit*'s color, lemon *channel* on tree *key*, or with no
    channel the whole tree, or its first lemon where the edit can't take a whole tree; or why not."""
    block = next((b for b in grove.blocks if b.digit == digit), None)
    if action not in ACTIONS:
        return f"no edit {action}"
    if block is None:
        return "that block is gone"
    if action == "color":
        return (
            picking.target(
                keys.Where(block=digit, editing=action),
                grove.blocks,
                grove.arrangement,
                block,
                None,
            )
            if block.name or block.home
            else "lemons in no group have no color"
        )

    tree = next((t for t in block.trees if t.key == key), None)
    if tree is None or (channel and not any(m.channel == channel for m in tree.lemons)):
        return "that lemon is gone"
    whole = "" in picking.edit_choices(action, tree)
    picked = channel or ("" if whole else tree.lemons[0].channel)
    where = keys.Where(block=digit, editing=action, picked_tree=key, picked_lemon=picked)
    return picking.target(where, grove.blocks, grove.arrangement, block, tree)


_RENUMBERING = ("home", "earlier", "later")


def _renumber(grove: Grove, action: str, digit: str) -> str:
    block = next((b for b in grove.blocks if b.digit == digit), None)
    if block is None:
        return "that block is gone"
    if action == "home":
        return block_numbers.set_home("" if block.home else block.name)
    return block_numbers.renumber(grove.blocks, digit, -1 if action == "earlier" else 1)


def placed(grove: Grove, channel: str) -> tuple[str, str] | None:
    """The block digit and tree key the grove shows lemon *channel* under, for a page that knows
    only the lemon."""
    return next(
        (
            (b.digit, t.key)
            for b in grove.blocks
            for t in b.trees
            if any(m.channel == channel for m in t.lemons)
        ),
        None,
    )


def info(grove: Grove, config: Config, action: str, digit: str, key: str, channel: str) -> dict:
    """What the page's dialog for the edit shows: what it changes, and the choices it offers."""
    target = _target(grove, action, digit, key, channel)
    if isinstance(target, str):
        return {"problem": target}

    where = keys.Where(block=digit, editing=action, picked_tree=key, picked_lemon=target.channel)
    now = time.time()
    return {
        "problem": "",
        "what": picking.prompt(where, grove.blocks),
        "name": target.name,
        "presets": [
            [preset, snooze_time.describe(preset, now, config.inbox.snooze_day_starts)]
            for preset in config.inbox.snooze_presets
        ]
        if action == "snooze"
        else [],
        "groups": changes.group_names(target) if action == "group" else [],
        "trees": [list(choice) for choice in target.trees],
        "color": changes.saved_color(target) if action == "color" else "",
        "syntax": snooze_time.SYNTAX,
    }


def make(
    grove: Grove,
    config: Config,
    action: str,
    digit: str,
    key: str,
    channel: str,
    answer: str,
    rename_session: abc.Callable[[str, str], str] | None,
) -> str:
    """Make the edit with the dialog's *answer*; what happened, or why it didn't.
    *rename_session(old, new)* renames a tree's tmux session; without it, only lemons are renamed."""
    if action in _RENUMBERING:
        return _renumber(grove, action, digit)

    target = _target(grove, action, digit, key, channel)
    if isinstance(target, str):
        return target

    if action == "rename":
        return renames.apply(dataclasses.replace(target, name=answer), rename_session)
    if action == "snooze":
        until = snooze_time.parse_wake(answer, time.time(), config.inbox.snooze_day_starts)
        return f"Enter {snooze_time.SYNTAX}" if until is None else changes.snooze(target, until)
    if action == "archive":
        return changes.archive(target)
    if action == "pin":
        return changes.pin(target)
    if action == "group":
        return changes.move(target, answer) if answer else "no group chosen"
    if action == "graft":
        return changes.graft(target, answer)
    return changes.recolor(target, answer)
