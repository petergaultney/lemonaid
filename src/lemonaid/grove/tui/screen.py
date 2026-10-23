"""The grove as a full-screen Textual screen."""

import dataclasses
import math
from collections import abc

from textual import events
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.strip import Strip
from textual.widget import Widget

from ..draw import canvas
from . import compass, keys, picking
from .frame import Grove, Lists, clamp_pan, render
from .rename_dialog import RenameDialog

_PULSE_LEVELS = 8  # frames in half a pulse; the other half replays them backwards
_TICK = 0.2


class GroveMap(Widget):
    DEFAULT_CSS = "GroveMap { width: 100%; height: 100%; }"

    def __init__(self) -> None:
        super().__init__()
        self.picture: canvas.Canvas | None = None

    def render_line(self, y: int) -> Strip:
        if self.picture is None or y >= self.picture.height:
            return Strip.blank(self.size.width)

        return Strip(canvas.line_segments(self.picture.rows[y]), self.picture.width)

    def target_at(self, x: int, y: int) -> tuple[str, ...]:
        if self.picture is None or not (
            0 <= y < self.picture.height and 0 <= x < self.picture.width
        ):
            return ()

        return self.picture.rows[y][x].target


class GroveScreen(ModalScreen[str]):
    """Dismisses with the channel of the chosen lemon, or "" when closed without one.

    Modal, so the inbox's own bindings (its priority arrow keys among them) stand aside.
    """

    DEFAULT_CSS = "GroveScreen { background: #0b0e13; }"

    def __init__(
        self,
        load: abc.Callable[[], Grove],
        refresh_every: float = 2.0,
        note: str = "",
        rename: abc.Callable[[picking.Rename], str] | None = None,
        pan: tuple[float, float] = (0.0, 0.0),
        keep_pan: abc.Callable[[tuple[float, float]], None] | None = None,
        nudge: tuple[int, int] = (2, 1),
        held: bool = False,
        lists: Lists | None = None,
    ) -> None:
        """*rename* carries out a rename and says what happened; without it, nothing renames.
        The view starts at *pan*, and *keep_pan* is told where it moves, to start there next time;
        an arrow moves it *nudge* cells, across and down. A *held* grove doesn't pulse until
        `hold(False)`. *lists* remembers where lemon lists went, kept across groves that share it.
        """
        super().__init__()
        self._load = load
        self._rename = rename
        self._refresh_every = refresh_every
        self._grove = load()
        self._where = keys.Where(note=note, pan=pan)
        self._keep_pan = keep_pan
        self._nudge = nudge
        self._loading = False
        self._tick = 0
        self._frames: dict[int, canvas.Canvas] = {}
        self._was_open = False  # whether the last key arrived zoomed in or searching
        self._held = held
        self._lists: Lists = {} if lists is None else lists

    def compose(self) -> ComposeResult:
        yield GroveMap()

    def on_mount(self) -> None:
        self._pulse_timer = self.set_interval(_TICK, self._pulse, pause=self._held)
        self.set_interval(self._refresh_every, self._reload)
        self._redraw()
        self._reload()  # what it was given may be a while old

    def on_resize(self, _event: events.Resize) -> None:
        self._redraw()

    def _phase_level(self) -> int:
        position = self._tick % (2 * _PULSE_LEVELS)
        return position if position < _PULSE_LEVELS else 2 * _PULSE_LEVELS - 1 - position

    def _redraw(self) -> None:
        self._frames.clear()
        self._show()

    def _show(self) -> None:
        level = self._phase_level()
        if level not in self._frames:
            phase = (1 - math.cos(math.pi * level / (_PULSE_LEVELS - 1))) / 2
            size = self.size
            self._frames[level] = render(
                self._grove, self._where, size.width, size.height, phase, self._lists
            )
        grove_map = self.query_one(GroveMap)
        grove_map.picture = self._frames[level]
        grove_map.refresh()

    def hold(self, held: bool) -> None:
        """Stop pulsing while nobody can see the grove; on showing again, catch up."""
        self._held = held
        if held:
            self._pulse_timer.pause()
            return

        self._pulse_timer.resume()
        self._reload()

    def _pulse(self) -> None:
        if not any(
            lemon.working
            for block in self._grove.blocks
            for tree in block.trees
            for lemon in tree.lemons
        ):
            return

        self._tick += 1
        self._show()

    def _reload(self) -> None:
        """Load in a thread: a fresh read of the inbox takes a quarter second or so."""
        if self._loading:
            return

        self._loading = True
        self.run_worker(self._fetch, thread=True, group="grove-load", exit_on_error=False)

    def _fetch(self) -> None:
        try:
            grove = self._load()
        finally:
            self.app.call_from_thread(setattr, self, "_loading", False)
        self.app.call_from_thread(self._apply, grove)

    def _apply(self, grove: Grove) -> None:
        if grove != self._grove:
            self._where = keys.reconcile(self._where, self._grove.blocks, grove.blocks)
            self._grove = grove
            self._redraw()

    def _press(self, key: str) -> None:
        if key == " " and self._where.search is None:
            self.dismiss("")
            return

        before = self._where.pan
        channel, rename = "", None
        if compass.handles(self._where, key):
            self._where = compass.step(
                self._grove, self._where, key, (self.size.width, self.size.height), self._nudge
            )
        else:  # only the compass moves the view: zooming, searching and picking keep it
            self._where, channel, rename = picking.step(
                self._where, key, self._grove.blocks, self._grove.arrangement
            )
            self._where = dataclasses.replace(self._where, pan=before)
        self._where = clamp_pan(self._grove, self._where, self.size.width, self.size.height)
        if self._where.pan != before and self._keep_pan:
            self._keep_pan(self._where.pan)
        if rename:
            self._ask_name(rename)
        if channel:
            self.dismiss(channel)
            return
        if key == "escape" and keys.at_rest(self._where) and not self._was_open:
            self.dismiss("")
            return
        self._redraw()

    def _ask_name(self, rename: picking.Rename) -> None:
        what = "lemon" if rename.channel else "tmux session"

        def renamed(name: str | None) -> None:
            if name is None:
                return

            note = (
                self._rename(dataclasses.replace(rename, name=name))
                if self._rename
                else "renaming needs lma or the popup"
            )
            self._where = dataclasses.replace(
                self._where, renaming=False, picked_tree="", picked_lemon="", note=note
            )
            self._reload()
            self._redraw()

        self.app.push_screen(RenameDialog(f"Rename {what} {rename.name}", rename.name), renamed)

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        if self._held:
            self.hold(False)
        self._was_open = not keys.at_rest(self._where)
        self._press(
            event.character
            if not event.key.startswith("alt+")
            and event.character
            and event.character.isprintable()
            and len(event.character) == 1
            else event.key
        )

    def on_click(self, event: events.Click) -> None:
        target = self.query_one(GroveMap).target_at(event.x, event.y)
        if not target:
            return

        if self._where.block != target[0]:
            self._where = keys.Where(block=target[0], digits=target[0])
            self._redraw()
            return
        if len(target) > 1:
            self._press(target[1])
