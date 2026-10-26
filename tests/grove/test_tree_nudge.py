import asyncio
import dataclasses

from lemonaid.grove.layout import state
from lemonaid.grove.tui import drop, tree_nudge
from lemonaid.grove.tui.app import GroveApp
from lemonaid.grove.tui.grove_map import GroveMap
from lemonaid.grove.tui.screen import GroveScreen

from .test_frame import GROVE

_TREE = "tars/slow-first-queries"
_SPOT = GROVE.arrangement.trees[("oria", _TREE)]


def test_arrows_step_one_unit_and_shift_five():
    assert tree_nudge.step("left") == (-1, 0)
    assert tree_nudge.step("shift+down") == (0, 5)
    assert tree_nudge.step("x") is None


def test_a_step_moves_the_tree_and_one_off_its_ground_leaves_it():
    drag = tree_nudge.start(GROVE, "1", _TREE)
    moved, problem = tree_nudge.nudged(GROVE, drag, (1, 0))
    assert (moved.moved, problem) == ((1, 0), "")
    stuck, problem = tree_nudge.nudged(GROVE, drag, (-1000, 0))
    assert (stuck.moved, problem) == ((0, 0), "a tree stays on its block's ground")


def test_a_step_onto_another_tree_hops_past_it():
    drag = tree_nudge.start(GROVE, "1", _TREE)
    assert drop.refused(GROVE, dataclasses.replace(drag, moved=(12, 0)))
    moved, problem = tree_nudge.nudged(GROVE, dataclasses.replace(drag, moved=(11, 0)), (1, 0))
    assert (moved.moved, problem) == ((23, 0), "")


def test_arrows_move_a_tree_chosen_whole_and_save_it_once_they_stop():
    state.save(GROVE.saved)
    letter = _SPOT.letter

    async def run() -> None:
        app = GroveApp(lambda: GROVE, 60.0, None)
        async with app.run_test(size=(160, 48)) as pilot:
            while not isinstance(app.screen, GroveScreen):  # it opens from a worker
                await pilot.pause()
            await pilot.press("tab", "1", "$", letter, "right", "right", "escape")
            await app.workers.wait_for_complete()
            await pilot.pause()

    asyncio.run(run())
    assert state.load()["trees"]["oria"][_TREE]["x"] == _SPOT.cx + 2


def test_a_mouse_drop_after_a_keyboard_move_is_not_undone_by_its_save():
    state.save(GROVE.saved)
    letter = _SPOT.letter

    async def run() -> None:
        app = GroveApp(lambda: GROVE, 60.0, None)
        async with app.run_test(size=(160, 48)) as pilot:
            while not isinstance(app.screen, GroveScreen):  # it opens from a worker
                await pilot.pause()
            await pilot.press("tab", "1", "$", letter, "right")
            grove_map = app.screen.query_one(GroveMap)
            x, y = next(
                (x, y)
                for y, row in enumerate(grove_map.picture.rows)
                for x, cell in enumerate(row)
                if cell.target == ("1", letter)
            )
            await pilot.mouse_down(GroveMap, offset=(x, y))
            across = round(2 * app.screen._drag.scale[0])
            await pilot.hover(GroveMap, offset=(x + across, y))
            await pilot.mouse_up(GroveMap, offset=(x + across, y))
            await app.workers.wait_for_complete()
            await asyncio.sleep(0.8)  # past the keyboard move's save
            await app.workers.wait_for_complete()
            await pilot.pause()

    asyncio.run(run())
    assert state.load()["trees"]["oria"][_TREE]["x"] == _SPOT.cx + 3
