import asyncio
import threading

from textual import events

from lemonaid.grove.tui.app import GroveApp
from lemonaid.grove.tui.grove_map import GroveMap
from lemonaid.grove.tui.screen import GroveScreen

from .test_frame import GROVE


def test_a_grove_that_hides_keeps_running_with_a_fresh_one_held_for_next_time():
    hidden = []

    async def run() -> tuple[bool, bool, bool]:
        app = GroveApp(lambda: GROVE, 60.0, lambda _: "", leave=lambda: hidden.append(True))
        async with app.run_test(size=(160, 48)) as pilot:
            first = app.screen
            await pilot.press("escape")
            await pilot.pause()
            held = app.screen._held
            await pilot.press("1")
            await pilot.pause()
            return (
                app.screen is not first and isinstance(app.screen, GroveScreen),
                held,
                (app.screen._held),
            )

    replaced, held, still_held = asyncio.run(run())
    assert hidden == [True]
    assert replaced and held and not still_held


def test_a_grove_started_held_reads_nothing_until_it_is_shown():
    loads = []

    def load():
        loads.append(True)
        return GROVE

    async def run() -> tuple[int, int]:
        app = GroveApp(load, 0.05, lambda _: "", leave=lambda: None, start_held=True)
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            while_held = len(loads)
            app.post_message(events.AppFocus())
            await pilot.pause(0.3)
            return while_held, len(loads)

    while_held, after_shown = asyncio.run(run())
    assert while_held == 1  # the first read, before it was held
    assert after_shown > while_held


def test_a_grove_shown_while_its_first_read_runs_starts_unheld():
    release = threading.Event()

    def load():
        release.wait(5)
        return GROVE

    async def run() -> bool:
        app = GroveApp(load, 0.05, lambda _: "", leave=lambda: None, start_held=True)
        async with app.run_test(size=(160, 48)) as pilot:
            app.post_message(events.AppFocus())
            await pilot.pause()
            release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            return isinstance(app.screen, GroveScreen) and not app.screen._held

    assert asyncio.run(run())


def test_an_edit_that_finishes_after_its_grove_closed_changes_no_screen():
    pending = []
    letter = GROVE.arrangement.trees[("relay", "git-sync-wedge")].letter

    async def run() -> bool:
        app = GroveApp(
            lambda: GROVE,
            60.0,
            lambda _app, _target, done: pending.append(done),
            leave=lambda: None,
        )
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("tab", "2", letter, "a")
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            pending[0]("archived 1 lemon")
            await pilot.pause()
            return app.is_running

    assert asyncio.run(run())
    assert len(pending) == 1


def test_the_grove_and_its_view_are_read_off_the_event_loop():
    readers = []

    def read(found):
        readers.append(threading.current_thread() is threading.main_thread())
        return found

    async def run() -> bool:
        app = GroveApp(
            lambda: read(GROVE), 60.0, None, leave=lambda: None, pan=lambda: read((0.0, 0.0))
        )
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            await pilot.press("escape")  # hides it, and a fresh grove waits, held
            await pilot.pause()
            return isinstance(app.screen, GroveScreen)

    assert asyncio.run(run())
    assert len(readers) >= 4 and not any(readers)


def test_select_mode_chooses_without_closing_and_enter_jumps():
    letter = GROVE.arrangement.trees[("relay", "git-sync-wedge")].letter

    async def run() -> tuple[str, bool, str]:
        app = GroveApp(lambda: GROVE, 60.0, None)
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("tab", "2", letter)
            await pilot.pause()
            chosen = app.screen._where.selected_lemon
            still_open = isinstance(app.screen, GroveScreen)
            await pilot.press("enter")
            await pilot.pause()
        return chosen, still_open, app.return_value

    assert asyncio.run(run()) == ("claude:wedge", True, "claude:wedge")


def test_an_edit_letter_in_select_mode_asks_for_its_edit():
    letter = GROVE.arrangement.trees[("relay", "git-sync-wedge")].letter
    asked = []

    async def run() -> None:
        app = GroveApp(lambda: GROVE, 60.0, lambda _app, target, _done: asked.append(target))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("tab", "2", letter, "p")
            await pilot.pause()

    asyncio.run(run())
    assert [(t.action, t.channel) for t in asked] == [("pin", "claude:wedge")]


def test_a_click_on_a_tree_in_select_mode_chooses_it_and_edits_nothing():
    first, other = (
        GROVE.arrangement.trees[("oria", key)].letter
        for key in ("oria-hq", "tars/slow-first-queries")
    )
    asked = []

    async def run() -> str:
        app = GroveApp(lambda: GROVE, 60.0, lambda _app, target, _done: asked.append(target))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("tab", "1", first)
            await pilot.pause()
            grove_map = app.screen.query_one(GroveMap)
            x, y = next(
                (x, y)
                for y, row in enumerate(grove_map.picture.rows)
                for x, cell in enumerate(row)
                if cell.target == ("1", other)
            )
            await pilot.click(GroveMap, offset=(x, y))
            await pilot.pause()
            return app.screen._where.selected_tree

    assert asyncio.run(run()) == other
    assert asked == []


def test_a_zoom_asked_for_while_the_grove_loads_applies_once_it_shows():
    release = threading.Event()
    taken = threading.Event()

    def load():
        assert release.wait(5)
        return GROVE

    def zoom_to() -> str:
        taken.set()
        return "2"

    async def run() -> str:
        app = GroveApp(load, 60.0, None, zoom_to=zoom_to)
        async with app.run_test(size=(160, 48)) as pilot:
            app.on_app_focus(events.AppFocus())
            assert await asyncio.to_thread(taken.wait, 2)
            await pilot.pause()
            release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, GroveScreen)
            return app.screen._where.block

    try:
        assert asyncio.run(run()) == "2"
    finally:
        release.set()


def test_a_zoom_asked_for_on_a_shown_grove_zooms_it():
    async def run() -> str:
        app = GroveApp(lambda: GROVE, 60.0, None, zoom_to=lambda: "2")
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            app.on_app_focus(events.AppFocus())
            await app.workers.wait_for_complete()
            await pilot.pause()
            return app.screen._where.block

    assert asyncio.run(run()) == "2"
