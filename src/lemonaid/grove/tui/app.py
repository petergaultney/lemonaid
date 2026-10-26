"""The grove on its own: an app that exits with the chosen lemon, or switches to it itself."""

from collections import abc

from textual import events
from textual.app import App

from . import flip, selecting
from .frame import Grove, Lists
from .screen import Edit, GroveScreen


class GroveApp(App[str]):
    """Exits with the chosen lemon's channel, or "" if none was chosen.

    With *choose*, it switches to the lemon itself: *choose* returns why it couldn't, or "",
    and on a failure the grove stays open to say so. *leave*, when given, is called instead of
    exiting the app, for a grove that keeps running hidden: a fresh one waits, held, to be shown
    again. *pan* says
    where the view starts, *keep_pan* is told where it moves, and an arrow moves it *nudge* cells.
    """

    CSS = "Screen { background: #0b0e13; }"

    def __init__(
        self,
        load: abc.Callable[[], Grove],
        refresh_every: float,
        edit: Edit | None,
        choose: abc.Callable[[str], str] | None = None,
        leave: abc.Callable[[], None] | None = None,
        pan: abc.Callable[[], tuple[float, float]] = lambda: (0.0, 0.0),
        keep_pan: abc.Callable[[tuple[float, float]], None] | None = None,
        nudge: tuple[int, int] = (2, 1),
        big_trees: bool = False,
        flips: flip.Flip = flip.DEFAULT,
        select_key: str = selecting.DEFAULT_KEY,
    ) -> None:
        super().__init__()
        self._edit = edit
        self._load = load
        self._refresh_every = refresh_every
        self._choose = choose
        self._leave = leave
        self._pan = pan
        self._keep_pan = keep_pan
        self._nudge = nudge
        self._big_trees = big_trees
        self._flips = flips
        self._select_key = select_key
        self._lists: Lists = {}  # where lemon lists went, kept from one grove shown to the next

    def on_mount(self) -> None:
        self._open()

    def _open(self, note: str = "", held: bool = False) -> None:
        """Reads the grove and where the view was in a thread, as a refresh does: both read files."""
        self.run_worker(lambda: self._read(note, held), thread=True, group="grove-open")

    def _read(self, note: str, held: bool) -> None:
        grove, pan = self._load(), self._pan()
        self.call_from_thread(self._push, grove, pan, note, held)

    def _push(self, grove: Grove, pan: tuple[float, float], note: str, held: bool) -> None:
        self.push_screen(
            GroveScreen(
                self._load,
                self._refresh_every,
                note,
                self._edit,
                pan,
                self._keep_pan,
                self._nudge,
                held,
                self._lists,
                self._big_trees,
                self._flips,
                grove,
                self._select_key,
            ),
            self._after_screen,
        )

    def _after_screen(self, channel: str | None) -> None:
        problem = self._choose(channel) if channel and self._choose else ""
        if problem:
            self._open(problem)
            return
        if self._leave:
            self._leave()
            self._open(held=True)
            return

        self.exit(channel or "")

    def on_app_focus(self, _event: events.AppFocus) -> None:
        if isinstance(self.screen, GroveScreen):
            self.screen.hold(False)
