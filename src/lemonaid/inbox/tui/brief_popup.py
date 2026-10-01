"""The brief popup: one brief view in its own app, with the scratch pane's question keys."""

from collections import abc

from textual import events
from textual.app import App, ComposeResult
from textual.screen import ModalScreen

from ...brief import pr, target
from ...config import Config
from .brief_view import BriefView


def _pressed(event: events.Key) -> str:
    """The key as `brief.dismiss` names it: the character typed, or Textual's name for the key."""
    return event.character if event.character and event.character.isprintable() else event.key


class BriefPopup(App[None]):
    BINDINGS = [("q", "quit", "Close"), ("escape", "quit", "Close")]

    def __init__(
        self, found: target.Target, config: Config, dismiss: abc.Iterable[tuple[str, str]] = ()
    ) -> None:
        super().__init__()
        self._found = found
        self._config = config
        self._dismiss = frozenset(dismiss)
        self._last_key = ""
        if config.tui.transparent:
            self.ansi_color = True

    def compose(self) -> ComposeResult:
        yield BriefView(
            pr.configured(self._config.brief.pr_state),
            self._config.brief.vaults,
            self._config.tui.keybindings,
            self._config.tui.mid_turn_working,
            self._config.places.roots,
        )

    def on_mount(self) -> None:
        if self._config.tui.transparent:
            self.screen.styles.background = "transparent"
        view = self.query_one(BriefView)
        view.show(self._found)
        view.focus()
        # PR states arrive in the background, and the brief can change while it is open.
        self.set_interval(self._config.tui.refresh_interval, lambda: view.update_brief(self._found))

    def on_key(self, event: events.Key) -> None:
        """Close on the tmux key that opened the popup, which reaches it as two keys."""
        if isinstance(self.screen, ModalScreen):
            return

        pressed = _pressed(event)
        if (self._last_key, pressed) in self._dismiss:
            self.exit()
        self._last_key = pressed


def run(found: target.Target, config: Config, dismiss: abc.Iterable[tuple[str, str]] = ()) -> None:
    BriefPopup(found, config, dismiss).run()
