"""Keys bound to more than one action in the same TUI view."""

import typing as ty
import unicodedata
from collections import abc

if ty.TYPE_CHECKING:
    from .config import KeybindingsConfig

_JUMP_DIGITS = "1234567890"
# Textual's key names whose Unicode names have a hyphen where the key name has `_`.
_HYPHENATED = {"hyphen_minus": "-", "less_than_sign": "<", "greater_than_sign": ">"}


def _name(key: str) -> str:
    """One spelling per key: `(` and `left_parenthesis` are the same key."""
    if len(key) == 1 or "+" in key:
        return key

    try:
        return _HYPHENATED.get(key) or unicodedata.lookup(key.replace("_", " ").upper())
    except KeyError:
        return key


def _shared(kb: "KeybindingsConfig") -> dict[str, abc.Iterable[str]]:
    """Actions bound in both the inbox list and the scratch pane's brief view."""
    up, down = kb.up_down if len(kb.up_down) == 2 else ("", "")
    return {
        "quit": kb.quit,
        "refresh": kb.refresh,
        "mark_read": kb.mark_read,
        "mark_unread": kb.mark_unread,
        "rename": kb.rename,
        "undo": kb.undo,
        "brief": [*kb.brief, kb.brief_key],
        "flip_position": kb.flip_position,
        "help": ["?"],
        "up": ["up", up],
        "down": ["down", down],
    }


def _inbox(kb: "KeybindingsConfig") -> dict[str, abc.Iterable[str]]:
    return {
        **_shared(kb),
        "select": [*kb.select, "enter"],
        "jump_unread": kb.jump_unread,
        "archive": kb.archive,
        "snooze": kb.snooze,
        "snoozed_list": kb.snoozed_list,
        "history": kb.history,
        "copy_resume": kb.copy_resume,
        "resume_detached": kb.resume_detached,
        "tmux_resume": kb.tmux_resume,
        "pin": kb.pin,
        "toggle_group": [kb.group_key],
        "group_tree": kb.group_tree,
        "group_add": kb.group_add,
        "group_remove": kb.group_remove,
        "move_pin_up": [kb.move_pin_up],
        "move_pin_down": [kb.move_pin_down],
        "first": [kb.first, "home"],
        "last": [kb.last, "end"],
        "save_size": kb.save_size,
        "fold": kb.fold,
        "notes": kb.notes,
        "search": [kb.search],
        "patch_claude": ["P"],
        **({f"jump_to_{d}": [d] for d in _JUMP_DIGITS} if kb.jump_by_number else {}),
    }


def _brief(kb: "KeybindingsConfig") -> dict[str, abc.Iterable[str]]:
    return {
        **_shared(kb),
        "question_previous": [kb.question_previous],
        "question_next": [kb.question_next],
        "answer": [kb.answer],
        "answer_yes": [kb.answer_yes],
        "more_detail": [kb.more_detail],
    }


def _conflicts(view: str, actions: abc.Mapping[str, abc.Iterable[str]]) -> abc.Iterator[str]:
    bound: dict[str, list[str]] = {}
    for action, keys in actions.items():
        for key in dict.fromkeys(_name(key) for key in keys if key):
            bound.setdefault(key, []).append(action)

    for key, names in bound.items():
        if len(names) > 1:
            yield f"in the {view} view, {key!r} is bound to {' and '.join(names)}"


def conflicts(kb: "KeybindingsConfig") -> list[str]:
    return [*_conflicts("inbox", _inbox(kb)), *_conflicts("brief", _brief(kb))]
