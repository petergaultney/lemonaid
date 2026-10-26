import asyncio

import pytest

from lemonaid.grove.tui import flip, help_panel, picking
from lemonaid.grove.tui.app import GroveApp
from lemonaid.grove.tui.screen import GroveScreen

from .test_frame import GROVE


def test_the_panel_lists_every_edit_in_both_views():
    for zoomed in (False, True):
        keys = {key for key, _ in help_panel.rows(zoomed)}
        assert {f"Alt+{key[4:]}" for key in picking.ACTIONS} <= keys, keys
        assert {"?", "esc", "space"} <= keys


def test_both_views_list_the_flip_key_as_configured():
    assert "branch" in dict(help_panel.rows(True))["hold ;"]
    assert "1/3" in dict(help_panel.rows(False))["hold ;"]
    toggled = dict(help_panel.rows(True, flip.Flip("\\", hold=False)))
    assert "again" in toggled["\\"]


def test_question_mark_shows_the_keys_over_the_grove_and_any_key_closes_them():
    async def run() -> list[object]:
        app = GroveApp(lambda: GROVE, 60.0, lambda _: "")
        async with app.run_test(size=(160, 48)) as pilot:
            seen = []
            for keys in (["question_mark"], ["x"], ["1", "question_mark"], ["escape"]):
                for key in keys:
                    await pilot.press(key)
                await pilot.pause()
                panels = app.screen.query(help_panel.HelpPanel)
                seen.append(
                    (
                        type(app.screen),
                        panels.first()._zoomed if panels else None,
                        app.screen._where.block,
                    )
                )
            return seen

    assert asyncio.run(run()) == [
        (GroveScreen, False, ""),
        (GroveScreen, None, ""),
        (GroveScreen, True, "1"),
        (GroveScreen, None, "1"),  # the key that closes it does nothing else
    ]


def test_question_mark_is_typed_into_a_search():
    async def run() -> tuple[type, str | None]:
        app = GroveApp(lambda: GROVE, 60.0, lambda _: "")
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("slash", "question_mark")
            await pilot.pause()
            return type(app.screen), app.screen._where.search

    assert asyncio.run(run()) == (GroveScreen, "?")


def test_recoloring_says_it_needs_only_a_block():
    grove, block = dict(help_panel.rows(False)), dict(help_panel.rows(True))
    assert "after a block's digit" in grove["Alt+c"] and "at once" in block["Alt+c"]
    assert "packhouse has no color" in block["Alt+c"]


def test_the_panel_teaches_the_dot_the_letter_and_a_place():
    assert ".c1" in dict(help_panel.rows(True))["a dot, a letter, a place"]
    assert "2.c1" in dict(help_panel.rows(False))["a digit, a dot, a letter, a place"]


@pytest.mark.parametrize(("width", "height"), [(160, 46), (80, 24)])
def test_the_panel_opens_centred_and_inside_the_screen(width, height):
    async def run():
        app = GroveApp(lambda: GROVE, 60.0, lambda _: "")
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.press("question_mark")
            await pilot.pause()
            await pilot.pause()
            panel = app.screen.query_one(help_panel.HelpPanel)
            return panel.region

    region = asyncio.run(run())
    assert region.x >= 0 and region.y >= 0
    assert region.right <= width and region.bottom <= height
    assert abs((width - region.right) - region.x) <= 1
