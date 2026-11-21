"""The dialog that picks the tree to graft a lemon onto: the group picker's, without new names."""

from collections import abc

from ...inbox.tui.edits import group_picker


class TreePickerScreen(group_picker.GroupPickerScreen):
    """Dismisses with the chosen tree's main lemon's channel, "" to ungraft, or None on cancel."""

    SCOPED_CSS = False  # scoped to this class, the group picker's rules would match nothing
    PLACEHOLDER = "type to narrow"
    HINT = "Enter to graft, Up/Down to pick, Escape to cancel"

    def __init__(self, title: str, trees: abc.Sequence[tuple[str, str]]) -> None:
        super().__init__(title, ())
        self._trees = tuple(trees)

    def _choices(self, typed: str) -> list[tuple[str, str]]:
        wanted = typed.strip().casefold()
        return [(channel, label) for channel, label in self._trees if wanted in label.casefold()]
