"""The key reference, as a modal.

The footer holds one row, which a sidebar is too narrow to spend on a list that
grows every time a key is added. A modal takes the whole pane instead, so the
same reference reads the same in either layout.
"""

from collections.abc import Iterator

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Label, Static

from ...config import KeybindingsConfig

# Description per keybinding field, in the order they are shown. Fields absent
# from here are not user-facing keys and are left out.
_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Moving around",
        [
            ("select", "Switch to the selected session"),
            ("jump_unread", "Jump to the earliest unread session"),
            ("history", "Toggle session history"),
            ("snoozed_list", "Show snoozed sessions"),
        ],
    ),
    (
        "Acting on a session",
        [
            ("mark_read", "Mark as read"),
            ("mark_unread", "Mark as unread"),
            ("archive", "Archive - remove it from the list"),
            ("snooze", "Snooze until a time you pick"),
            ("rename", "Rename (clear it to go back to the auto name)"),
            ("undo", "Undo the last inbox change"),
        ],
    ),
    (
        "Pinning",
        [
            ("pin", "Pin the selected session, or unpin it"),
            ("move_pin_up", "Move a pinned session up one slot"),
            ("move_pin_down", "Move a pinned session down one slot"),
        ],
    ),
    (
        "The pane",
        [
            ("flip_position", "Move the scratch pane between top and left"),
            ("save_size", "Save the scratch pane size (follow mode)"),
            ("refresh", "Refresh now"),
            ("quit", "Quit"),
        ],
    ),
]


def _key_display(value: str, field: str) -> str:
    """How a configured key reads in the reference.

    Most fields hold a set of single-character alternatives; the pin-move fields
    hold one key name, which may carry a modifier.
    """
    if field in ("move_pin_up", "move_pin_down"):
        return value.replace("shift+", "Shift+").replace("ctrl+", "Ctrl+")

    return " / ".join(value)


def help_lines(kb: KeybindingsConfig) -> list[tuple[str, list[tuple[str, str]]]]:
    """The reference as (section, [(keys, description)]), skipping unbound keys.

    Built from the live configuration rather than a written-out list, so a
    rebound or unbound key says so instead of going stale.
    """
    return [
        (
            title,
            [
                (_key_display(getattr(kb, field), field), description)
                for field, description in entries
                if getattr(kb, field, "")
            ],
        )
        for title, entries in _SECTIONS
    ]


def _close_hint(kb: KeybindingsConfig) -> str:
    return ", ".join([*kb.quit, "Esc", "?"][:3]) if kb.quit else "Esc or ?"


# Only these close the reference. A sidebar's single column scrolls, so the keys
# that reach the rest of it have to keep working. Scoped to the modal: what these
# do in the inbox is unaffected.
_CLOSE_KEYS = frozenset({"escape", "q", "question_mark"})


def _section_widgets(sections: list[tuple[str, list[tuple[str, str]]]]) -> Iterator[Widget]:
    for title, entries in sections:
        yield Label(title, classes="section")
        for keys, description in entries:
            yield Static(f"[b]{keys:<12}[/b] {description}")


def _halves(
    sections: list[tuple[str, list[tuple[str, str]]]],
) -> list[list[tuple[str, list[tuple[str, str]]]]]:
    """Split into two columns of roughly equal height, keeping section order.

    Measured in rendered lines rather than section count, since the sections are
    not the same length - splitting down the middle by count left one column
    twice the height of the other, which is the scrolling this avoids.
    """
    heights = [2 + len(rows) for _title, rows in sections]  # the blank line above each
    total = sum(heights)
    best = min(
        range(1, len(sections)),
        key=lambda cut: abs(sum(heights[:cut]) - (total - sum(heights[:cut]))),
    )
    return [sections[:best], sections[best:]]


class HelpScreen(ModalScreen[None]):
    """The key reference. Any key closes it."""

    CSS = """
    HelpScreen {
        align: center middle;
    }

    HelpScreen > Vertical {
        width: 100%;
        max-width: 72;
        height: auto;
        max-height: 100%;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    /* A pane wider than it is tall has the room to lay the sections out side by
       side, which is what keeps a short one from scrolling. */
    HelpScreen.-wide > Vertical {
        max-width: 100%;
    }

    HelpScreen.-wide .columns {
        layout: horizontal;
        height: auto;
    }

    HelpScreen.-wide .column {
        width: 1fr;
        height: auto;
        padding-right: 2;
    }

    HelpScreen .title {
        width: 100%;
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

    HelpScreen .section {
        color: $text-muted;
        text-style: bold;
        padding-top: 1;
    }

    HelpScreen VerticalScroll > Static {
        padding-left: 2;
    }

    HelpScreen .hint {
        color: $text-muted;
        text-style: italic;
        padding-top: 1;
        text-align: center;
    }
    """

    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, keybindings: KeybindingsConfig, wide: bool = False) -> None:
        super().__init__()
        self.keybindings = keybindings
        self.wide = wide

    def compose(self) -> ComposeResult:
        sections = [(title, rows) for title, rows in help_lines(self.keybindings) if rows]
        with Vertical():
            yield Label("Keys", classes="title")
            if self.wide:
                with Horizontal(classes="columns"):
                    for half in _halves(sections):
                        with Vertical(classes="column"):
                            yield from _section_widgets(half)
            else:
                with VerticalScroll():
                    yield from _section_widgets(sections)
            yield Label("q, Esc, or ? to close", classes="hint")

    def on_mount(self) -> None:
        self.set_class(self.wide, "-wide")

    def on_key(self, event: events.Key) -> None:
        if event.key not in _CLOSE_KEYS:
            return

        # Stopped, or the key carries on to the app underneath - where escape is
        # bound to quit, so closing the reference closed lemonaid with it.
        event.stop()
        event.prevent_default()
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
