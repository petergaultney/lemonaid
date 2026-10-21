"""The inbox's key bindings, built from config."""

import dataclasses
from collections import abc

from textual.binding import Binding

from ... import keys
from ...config import Config, KeybindingsConfig
from .utils import JUMP_DIGITS


def build_bindings(keys: str, action: str, label: str, show: bool = True) -> list[Binding]:
    """One binding per character of *keys*; only the first is shown in the footer."""
    if not keys:
        return []

    # make_bindings turns a character into Textual's key name, `+` into `plus`,
    # but takes a comma for a separator.
    names = ["comma" if key == "," else key for key in keys]
    return list(
        Binding.make_bindings(
            [
                Binding(names[0], action, label, show=show),
                *(Binding(key, action, label, show=False) for key in names[1:]),
            ]
        )
    )


def _priority(key: str, action: str, label: str) -> Binding:
    return Binding(key, action, label, show=False, priority=True)


def _hidden(key: str, action: str, label: str) -> Binding:
    return Binding(key, action, label, show=False)


def _bindings(config: Config) -> abc.Iterator[Binding]:
    kb = config.tui.keybindings
    yield from build_bindings(kb.quit, "quit", "Quit")
    yield _hidden("escape", "back", "Quit")

    # Enter always selects through DataTable; these are additional keys.
    yield from build_bindings(kb.select, "select", "Switch")
    yield _priority("enter", "select_brief", "Switch")

    yield from build_bindings(kb.refresh, "refresh", "Refresh", show=False)
    yield from build_bindings(kb.jump_unread, "jump_unread", "Jump Unread")
    yield from build_bindings(kb.mark_read, "mark_read", "Mark Read")
    if keys.key_names(kb.mark_unread) == [kb.mark_unread] and len(kb.mark_unread) > 1:
        yield Binding(kb.mark_unread, "mark_unread", "Mark Unread")
    else:
        yield from build_bindings(kb.mark_unread, "mark_unread", "Mark Unread")
    yield from build_bindings(kb.hide, "hide", "Hide/show", show=False)
    yield from build_bindings(kb.archive, "archive", "Archive")
    yield from build_bindings(kb.rename, "rename", "Rename")
    yield from build_bindings(kb.snooze, "snooze", "Snooze")
    yield from build_bindings(kb.snoozed_list, "toggle_snoozed", "Snoozed")
    yield from build_bindings(kb.usage_view, "toggle_usage", "Usage")
    yield from build_bindings(kb.undo, "undo", "Undo")
    yield from build_bindings(kb.history, "toggle_history", "History")
    yield from build_bindings(kb.copy_resume, "copy_resume", "Copy", show=False)
    yield from build_bindings(kb.resume_detached, "resume_detached", "Resume")

    yield from build_bindings(kb.brief, "brief", "Brief")
    if kb.brief_key:
        # Textual gives Tab to focus-next, so this has to come first; check_action
        # hands the key back where something else wants it.
        yield _priority(kb.brief_key, "brief", "Brief")
    if kb.group_key:
        yield _priority(kb.group_key, "toggle_group", "Group")  # priority as brief_key's

    yield from build_bindings(kb.pin, "pin", "Pin")
    yield from build_bindings(kb.group_tree, "group_tree", "Group", show=False)
    yield from build_bindings(kb.group_add, "group_add", "Group", show=False)
    yield from build_bindings(kb.group_remove, "group_remove", "Group", show=False)
    yield from build_bindings(kb.group_color, "group_color", "Color", show=False)

    if config.tui.fold_statuses or config.inbox.arrange:
        yield from build_bindings(kb.fold, "toggle_fold", "Folded")

    if config.tui.notes is not None:
        yield from build_bindings(kb.notes, "toggle_notes", "Notes")

    # Named keys rather than a string of alternatives: these carry a modifier.
    if kb.move_pin_up:
        yield _hidden(kb.move_pin_up, "move_pin_up", "Move Up")
    if kb.move_pin_down:
        yield _hidden(kb.move_pin_down, "move_pin_down", "Move Down")

    # Priority, so that a table's own Home/End, a sideways scroll, loses to these.
    # check_action hands them back to an Input, a dialog and the brief view.
    for key in dict.fromkeys((kb.first, "home")):
        if key:
            yield _priority(key, "cursor_first", "Top")
    for key in dict.fromkeys((kb.last, "end")):
        if key:
            yield _priority(key, "cursor_last", "Bottom")

    yield from build_bindings(kb.tmux_resume, "tmux_resume", "Tmux", show=False)

    if kb.search:
        yield _hidden("slash" if kb.search == "/" else kb.search, "filter_history", "Search")

    yield _hidden("ctrl+t", "patch_claude", "Patch Claude")

    # Key hints share the bottom row with the status text, so they're a toggle
    # rather than a permanent fixture. Hidden from the footer it controls.
    yield _hidden("question_mark", "help", "Keys")

    yield from build_bindings(kb.flip_position, "flip_position", "Flip", show=False)
    if kb.save_size:
        yield _hidden(kb.save_size, "save_scratch_size", "Save Size")

    if kb.jump_by_number:
        for digit in JUMP_DIGITS:
            yield _hidden(digit, f"jump_to_number('{digit}')", "Jump")

    # Cross-table arrows, always active.
    yield _priority("up", "cursor_up", "Up")
    yield _priority("down", "cursor_down", "Down")

    if len(kb.up_down) == 2:  # vim-style, if configured
        up, down = kb.up_down
        yield _hidden(up, "cursor_up", "Up")
        yield _hidden(down, "cursor_down", "Down")


def app_bindings(config: Config) -> list[Binding]:
    return list(_bindings(config))


def help_keys(config: Config) -> KeybindingsConfig:
    """The keybindings the reference lists: the fold and notes keys only when bound."""
    kb = config.tui.keybindings
    if not (config.tui.fold_statuses or config.inbox.arrange):
        kb = dataclasses.replace(kb, fold="")
    if config.tui.notes is None:
        kb = dataclasses.replace(kb, notes="")
    return kb


def set_footer(
    key_to_bindings: dict[str, list[Binding]],
    action: str,
    *,
    show: bool | None = None,
    label: str | None = None,
) -> None:
    """Show or hide the first binding for *action* in the footer, or relabel all of them."""
    found = False
    for key, bindings in key_to_bindings.items():
        for i, binding in enumerate(bindings):
            if binding.action != action:
                continue

            replacements: dict = {}
            if not found and show is not None:
                replacements["show"] = show
            if label is not None:
                replacements["description"] = label
            if replacements:
                key_to_bindings[key][i] = dataclasses.replace(binding, **replacements)
            found = True


# Only what acts on the row whose brief is shown and leaves it in the list.
_WHILE_BRIEF_SHOWN = frozenset(
    {
        "quit",
        "back",
        "brief",
        "refresh",
        "help",
        "flip_position",
        "cursor_up",
        "cursor_down",
        "select",
        "mark_read",
        "mark_unread",
        "undo",
        "rename",
    }
)
# Keys bound with priority, handed back to a dialog or a text box that wants them.
_YIELDING = frozenset(
    {"cursor_up", "cursor_down", "brief", "toggle_group", "cursor_first", "cursor_last"}
)


def permitted(
    action: str,
    *,
    brief_shown: bool,
    overlaid: bool,
    searching: bool,
    history_focused: abc.Callable[[], bool],
    resume_available: abc.Callable[[], bool],
) -> bool:
    """Whether *action* runs now. `overlaid` means a dialog is up or a text box has the keys."""
    if action == "select_brief":
        return brief_shown and not overlaid

    if action in _YIELDING and overlaid:
        return False

    if action in {"copy_resume", "tmux_resume"} and searching:
        return history_focused()

    if action == "resume_detached":
        return resume_available()

    return action in _WHILE_BRIEF_SHOWN if brief_shown else True
