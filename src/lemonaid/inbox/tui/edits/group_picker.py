"""The dialog that picks a group to put a lemon in, or names a new one."""

from collections import abc

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option

_NEW = "\0new"  # the option id of "New group: ...", which no group name can be


def choices(names: abc.Sequence[str], typed: str) -> list[tuple[str, str]]:
    """(option id, label) for each group whose name contains *typed*, then a new one.

    A new group is offered only for typed text that no group is called exactly.
    """
    wanted = typed.strip()
    matching = [(name, name) for name in names if wanted.casefold() in name.casefold()]
    if not wanted or any(name == wanted for name in names):
        return matching

    return [*matching, (_NEW, f"New group: {wanted}")]


class GroupPickerScreen(ModalScreen[str | None]):
    """Type to narrow the groups or name a new one; Enter takes the highlighted line.

    Dismisses with the group's name, or None on cancel.
    """

    CSS = """
    GroupPickerScreen {
        align: center middle;
    }

    GroupPickerScreen > Vertical {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    GroupPickerScreen Label {
        width: 100%;
        text-align: center;
        padding-bottom: 1;
    }

    GroupPickerScreen Input {
        width: 100%;
        margin-bottom: 1;
    }

    GroupPickerScreen OptionList {
        height: auto;
        max-height: 12;
    }

    GroupPickerScreen .hint {
        color: $text-muted;
        text-style: italic;
        padding-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("up", "step(-1)", "Previous group"),
        ("down", "step(1)", "Next group"),
    ]

    def __init__(self, title: str, names: abc.Sequence[str]) -> None:
        super().__init__()
        self._title = title
        self._names = tuple(names)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield Input(placeholder="type to narrow, or to name a new group", id="group-name")
            options = OptionList(id="group-options")
            options.can_focus = False
            yield options
            yield Label("Enter to add, Up/Down to pick, Escape to cancel", classes="hint")

    def _show(self, typed: str) -> None:
        options = self.query_one("#group-options", OptionList)
        options.clear_options()
        options.add_options([Option(label, id=id) for id, label in choices(self._names, typed)])
        options.highlighted = 0 if options.option_count else None

    def on_mount(self) -> None:
        self._show("")
        self.query_one("#group-name", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._show(event.value)

    def action_step(self, step: int) -> None:
        options = self.query_one("#group-options", OptionList)
        if options.option_count:
            options.highlighted = ((options.highlighted or 0) + step) % options.option_count

    def _pick(self, option_id: str | None) -> None:
        if option_id is None:
            return

        self.dismiss(
            self.query_one("#group-name", Input).value.strip() if option_id == _NEW else option_id
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._pick(event.option.id)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        options = self.query_one("#group-options", OptionList)
        if options.highlighted is not None:
            self._pick(options.get_option_at_index(options.highlighted).id)

    def action_cancel(self) -> None:
        self.dismiss(None)
