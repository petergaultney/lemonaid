"""The grove as a full-screen Textual screen."""

import dataclasses
import time
from collections import abc
from typing import Any

from textual import events
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.timer import Timer

from ..draw import canvas
from ..layout import edit, state
from . import (
    choice,
    compass,
    drop,
    flip,
    garden,
    help_panel,
    keys,
    picking,
    pulse,
    quitting,
    selecting,
    tree_nudge,
)
from .frame import Grove, Lists, clamp_pan, render
from .grove_map import GroveMap

# Asks for what an edit needs and makes it, over the app, then tells the callback what happened.
Edit = abc.Callable[[App, picking.Target, abc.Callable[[str], None]], None]


class GroveScreen(ModalScreen[str]):
    """Dismisses with the channel of the chosen lemon, or "" when closed without one.

    Modal, so the inbox's own bindings (its priority arrow keys among them) stand aside.
    """

    DEFAULT_CSS = "GroveScreen { background: #0b0e13; layers: base overlay; }"

    def __init__(
        self,
        load: abc.Callable[[], Grove],
        refresh_every: float = 2.0,
        note: str = "",
        edit: Edit | None = None,
        pan: tuple[float, float] = (0.0, 0.0),
        keep_pan: abc.Callable[[tuple[float, float]], None] | None = None,
        nudge: tuple[int, int] = (2, 1),
        held: bool = False,
        lists: Lists | None = None,
        big_trees: bool = False,
        flips: flip.Flip = flip.DEFAULT,
        grove: Grove | None = None,
        select_key: str = selecting.DEFAULT_KEY,
    ) -> None:
        """*edit* asks for and makes an edit chosen with Alt and a key, then says what happened;
        without it, nothing is edited.
        The view starts at *pan*, and *keep_pan* is told where it moves, to start there next time;
        an arrow moves it *nudge* cells, across and down. A *held* grove doesn't pulse until
        `hold(False)`. *lists* remembers where lemon lists went, kept across groves that share it.
        *big_trees* lets a zoomed block's trees grow past a grown tree's size. *flips* says which
        key flips the lemon lists to their other page, and how. A *grove* already loaded is
        shown first, in place of loading one here. *select_key* enters and leaves select mode.
        """
        super().__init__()
        self._load = load
        self._edit = edit
        self._refresh_every = refresh_every
        self._grove = load() if grove is None else grove
        self._where = keys.Where(note=note, pan=pan)
        self._keep_pan = keep_pan
        self._nudge = nudge
        self._big_trees = big_trees
        self._loading = False
        # The picture at rest and darkest, till it changes, for each page, so flipping between
        # them draws neither again.
        self._ends: dict[bool, pulse.Ends] = {}
        self._was_open = False  # whether the last key arrived zoomed in or searching
        self._held = held
        self._lists: Lists = {} if lists is None else lists
        self._drag: garden.Drag | None = None
        self._dragged = False  # the mouse moved since it was pressed, so its click isn't one
        self._drag_frame_due = False
        self._redraw_due = False
        self._flips = flips
        self._flipped = False
        self._flip_back: Timer | None = None
        self._select_key = select_key
        # A tree moved by arrow keys: the grove it moves from and how far, saved once they stop
        self._moving: tuple[Grove, garden.Drag] | None = None
        self._moved_save: Timer | None = None
        self._flashed: tuple[str, ...] = ()  # the target of a tree that couldn't move

    def compose(self) -> ComposeResult:
        yield GroveMap()

    def on_mount(self) -> None:
        self._pulse_timer = self.set_interval(pulse.TICK, self._pulse, pause=self._held)
        self.set_interval(self._refresh_every, self._reload)
        self._redraw()
        self._reload()  # what it was given may be a while old

    def on_resize(self, _event: events.Resize) -> None:
        self._redraw()
        for panel in self.query(help_panel.HelpPanel):
            panel.center()

    def _redraw(self) -> None:
        self._ends = {}
        self._show()

    def _redraw_soon(self) -> None:
        """A redraw once the keys already waiting are handled, so a held arrow moves the choice
        ahead of the picture instead of waiting on a frame for each press.
        """
        if not self._redraw_due:
            self._redraw_due = True
            self.call_after_refresh(self._redraw_now)

    def _redraw_now(self) -> None:
        self._redraw_due = False
        self._redraw()

    def _draw(self, phase: float) -> canvas.Canvas:
        drag = self._drag
        return render(
            drop.dragged(self._grove, drag) if drag else self._grove,
            self._where,
            self.size.width,
            self.size.height,
            phase,
            garden.loose(self._lists, drag) if drag else self._lists,
            self._big_trees,
            self._flipped,
            self._select_key,
            drag is None,
            self._flashed,
        )

    def _show(self) -> None:
        """The picture at this moment of the pulse; at rest while the grove is held, so a
        working lemon never waits out of sight at its darkest.
        """
        if self._flipped not in self._ends:
            self._ends[self._flipped] = pulse.ends(self._draw)
        grove_map = self.query_one(GroveMap)
        grove_map.picture = pulse.frame(
            self._ends[self._flipped], 0.0 if self._held else pulse.phase(time.monotonic())
        )
        grove_map.refresh()

    def hold(self, held: bool) -> None:
        """Stop pulsing while nobody can see the grove; on showing again, catch up."""
        self._held = held
        if held:
            self._pulse_timer.pause()
            self._show()
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
        if grove != self._grove and self._drag is None and self._moving is None:
            self._where = choice.reconcile(
                keys.reconcile(self._where, self._grove.blocks, grove.blocks),
                grove.blocks,
                grove.arrangement,
            )
            self._grove = grove
            self._redraw()

    def _flip(self) -> None:
        flipped, back = flip.pressed(self._flipped, self._flips.hold)
        if self._flip_back:
            self._flip_back.stop()
        self._flip_back = self.set_timer(back, self._unflip) if back else None
        if flipped != self._flipped:
            self._flipped = flipped
            self._show()

    def _unflip(self) -> None:
        self._flip_back = None
        self._flipped = False
        self._show()

    def _press(self, key: str) -> None:
        if key == self._flips.key and self._where.search is None:
            self._flip()
            return
        if key == " " and self._where.search is None:
            self.dismiss("")
            return
        if key == "?" and self._where.search is None:
            self.mount(
                help_panel.HelpPanel(
                    bool(self._where.block), self._flips, self._select_key, self._where.selecting
                )
            )
            return

        found = choice.chosen(self._where, self._grove.blocks, self._grove.arrangement)
        by = tree_nudge.step(key)
        if by and found and found[2] is None and self._where.selecting and not self._where.editing:
            self._move_tree(found[1].key, by)
            return

        before = self._where.pan
        channel, target = "", None
        if key != self._select_key and compass.handles(self._where, key):
            self._where = compass.step(
                self._grove, self._where, key, (self.size.width, self.size.height), self._nudge
            )
        else:  # only the compass moves the view: zooming, searching and picking keep it
            self._where, channel, target = selecting.step(
                self._where, key, self._grove.blocks, self._grove.arrangement, self._select_key
            )
            self._where = dataclasses.replace(self._where, pan=before)
        self._where = clamp_pan(self._grove, self._where, self.size.width, self.size.height)
        if self._where.pan != before and self._keep_pan:
            self._keep_pan(self._where.pan)
        if target and self._edit:
            self._edit(self.app, target, self._finished)
        elif target:
            self._finished("editing needs lma or the popup")
        if channel:
            self.dismiss(channel)
            return
        if key == "escape" and keys.at_rest(self._where) and not self._was_open:
            self.dismiss("")
            return
        self._redraw_soon()

    def _move_tree(self, tree_key: str, by: tuple[int, int]) -> None:
        base, drag = self._moving or (
            self._grove,
            tree_nudge.start(self._grove, self._where.block, tree_key),
        )
        if isinstance(drag, str):
            self._refuse(drag)
            return

        moved, problem = tree_nudge.nudged(base, drag, by)
        if problem:
            self._refuse(problem)
            return

        self._moving = base, moved
        self._grove = drop.dragged(base, moved)
        for spots in self._lists.values():  # its lemon list goes beside it again
            spots.pop(tree_key, None)
        if self._moved_save:
            self._moved_save.stop()
        self._moved_save = self.set_timer(0.6, self._save_moved)
        self._where = dataclasses.replace(
            self._where, note=f"moving tree {moved.name} · saved when the arrows stop"
        )
        self._redraw_soon()

    def _refuse(self, problem: str) -> None:
        """Flash the tree that can't move, and say why."""
        self._flashed = (self._where.block, self._where.selected_tree)
        self._where = dataclasses.replace(self._where, note=f"not moved: {problem}")
        self._redraw_soon()
        self.set_timer(0.25, self._unflash)

    def _unflash(self) -> None:
        self._flashed = ()
        self._redraw()

    def _save_moved(self) -> None:
        if self._moved_save:
            self._moved_save.stop()
        self._moved_save = None
        if self._moving is None:
            return

        base, drag = self._moving
        self._moving = None
        change = drop.drop(base, drag)
        self.run_worker(lambda: self._save(change), thread=True, group="grove-garden")

    def _finished(self, note: str) -> None:
        if self not in self.app.screen_stack:
            return  # closed while the edit ran

        self._where = dataclasses.replace(
            self._where, editing="", picked_tree="", picked_lemon="", note=note
        )
        self._reload()
        self._redraw()

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        if self._moving and tree_nudge.step(event.key) is None:  # saved before anything else
            self._save_moved()
        if self._drag:  # a key ends a drag; only esc, mid-drag, is spent putting it back
            dragging = self._dragged
            self._put_back("")
            if dragging and event.key == "escape":
                return
        match quitting.quit_for(self._where, event.character or ""):
            case quitting.Quit.CLOSE:
                self.dismiss("")
                return
            case quitting.Quit.PROCESS:
                self.app.exit()
                return
        if self.query(help_panel.HelpPanel):
            self.query(help_panel.HelpPanel).remove()
            return
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
        if self._dragged:
            self._dragged = False
            return

        target = self.query_one(GroveMap).target_at(event.x, event.y)
        if not target:
            return

        if self._where.block != target[0]:
            self._where = keys.Where(
                block=target[0], digits=target[0], selecting=self._where.selecting
            )
            self._redraw()
            return
        if len(target) < 2 or not target[1]:  # a bare tree has no letter
            return

        if self._where.selecting and not self._where.editing:
            self._where = selecting.choose_tree(
                self._where, target[1], self._grove.blocks, self._grove.arrangement
            )
            self._redraw()
        else:
            self._press(target[1])

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if self._moved_save:  # a tree moved by keys waits for the mouse: its drop may supersede it
            self._moved_save.stop()
            self._moved_save = None
        self._dragged = False
        self._drag = garden.grab(
            self._grove,
            self._where,
            (self.size.width, self.size.height),
            (event.x, event.y),
            self.query_one(GroveMap).target_at(event.x, event.y),
        )
        if self._drag:
            self.capture_mouse()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._drag is None:
            return

        drag = garden.follow(self._drag, (event.x, event.y))
        if drag.moved == self._drag.moved:
            return

        self._drag, self._dragged = drag, True
        if not self._drag_frame_due:  # a frame takes longer than the mouse takes to move
            self._drag_frame_due = True
            self.call_after_refresh(self._drag_frame)

    def _drag_frame(self) -> None:
        self._drag_frame_due = False
        if self._drag is None:
            return

        self._where = dataclasses.replace(self._where, note=drop.describe(self._grove, self._drag))
        self._redraw()

    def _put_back(self, note: str) -> None:
        self._drag = None
        self.release_mouse()
        self._save_moved()
        self._where = dataclasses.replace(self._where, note=note)
        self._redraw()

    def on_mouse_up(self, _event: events.MouseUp) -> None:
        drag = self._drag
        if drag and drag.moved == (0, 0) and self._dragged:  # dragged away and back
            self._put_back("")
            return
        if drag is None or drag.moved == (0, 0):
            self._drag = None
            self.release_mouse()
            self._save_moved()
            return

        problem = drop.refused(self._grove, drag)
        if problem:
            self._put_back(f"not dropped: {problem}")
            return

        change = drop.drop(self._grove, drag)
        if self._moving and self._moving[1].tree == drag.tree:  # the drop's spot replaces it
            self._moving = None
        self._grove = drop.dragged(self._grove, drag)
        for spots in self._lists.values():  # its lemon list goes beside it again
            spots.pop(drag.tree, None)
        self._put_back("")
        self.run_worker(lambda: self._save(change), thread=True, group="grove-garden")

    def _save(self, change: abc.Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        try:
            state.update(change)
            note = ""
        except edit.EditError as error:
            note = f"not dropped: {error}"
        self.app.call_from_thread(self._finished, note)
