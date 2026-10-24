import asyncio

from textual.widgets import Input

from lemonaid.grove.layout import labels
from lemonaid.grove.tui import keys, quitting
from lemonaid.grove.tui.app import GroveApp
from lemonaid.grove.tui.rename_dialog import RenameDialog

from .test_frame import GROVE

LETTER = GROVE.arrangement.trees[("relay", "git-sync-wedge")].letter


def test_q_is_never_a_trees_letter():
    assert "q" not in labels.LETTERS
    assert labels.pick_letter("quiet queue", set()) != "q"


def test_q_and_capital_q_quit_unless_searching():
    assert quitting.quit_for(keys.Where(block="2"), "q") is quitting.Quit.CLOSE
    assert quitting.quit_for(keys.Where(editing="rename"), "Q") is quitting.Quit.PROCESS
    assert quitting.quit_for(keys.Where(search=""), "q") is quitting.Quit.NO


def _run(
    *presses: str, where: keys.Where | None = None, leave: bool = True
) -> tuple[list[bool], bool, str]:
    hidden: list[bool] = []

    async def run() -> tuple[bool, str]:
        app = GroveApp(
            lambda: GROVE,
            60.0,
            lambda *_: "",
            leave=(lambda: hidden.append(True)) if leave else None,
        )
        async with app.run_test(size=(160, 48)) as pilot:
            if where:
                app.screen._where = where
            await pilot.press(*presses)
            await pilot.pause()
            return app.is_running, getattr(app.screen, "_where", keys.Where()).search or ""

    running, search = asyncio.run(run())
    return hidden, running, search


def test_q_hides_the_grove_from_a_zoomed_block_and_an_opened_tree():
    assert _run("2", "q")[0] == [True]
    assert _run("q", where=keys.Where(block="2", digits="2", tree=LETTER))[0] == [True]
    assert _run("alt+r", "q")[0] == [True]


def test_capital_q_exits_the_app_without_hiding():
    hidden, running, _ = _run("2", "Q")
    assert hidden == [] and not running


def test_q_is_typed_into_a_search():
    hidden, running, search = _run("/", "q", "Q")
    assert hidden == [] and running and search == "qQ"


def test_an_edits_dialog_takes_q_and_capital_q_as_text():
    async def run() -> tuple[bool, str]:
        app = GroveApp(
            lambda: GROVE,
            60.0,
            lambda app, target, done: app.push_screen(RenameDialog("Rename", "")),
            leave=lambda: None,
        )
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("alt+r", "2", LETTER, "enter")
            await pilot.pause()
            await pilot.press("q", "Q")
            await pilot.pause()
            return app.is_running, app.screen.query_one(Input).value

    assert asyncio.run(run()) == (True, "qQ")
