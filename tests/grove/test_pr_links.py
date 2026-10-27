import asyncio
import dataclasses
import threading

import pytest
from rich.text import Text

from lemonaid.grove.tui import flip
from lemonaid.grove.tui.app import GroveApp
from lemonaid.grove.tui.grove_map import GroveMap

from .test_frame import GROVE

URL = "https://github.com/example/project/pull/423"


@pytest.mark.parametrize("view", ["flipped", "card"])
def test_plain_click_opens_a_pr_without_switching_or_dragging_its_lemon(monkeypatch, view):
    block = GROVE.blocks[1]
    tree = block.trees[0]
    lemon = dataclasses.replace(tree.lemons[0], prs=(("423", URL),), branch="grove/pr-links")
    tree = dataclasses.replace(tree, lemons=(lemon,))
    block = dataclasses.replace(block, trees=(tree,))
    grove = dataclasses.replace(
        GROVE,
        blocks=(GROVE.blocks[0], block),
        cards={lemon.channel: (Text.assemble(("#423", f"link {URL}")),)},
    )
    letter = grove.arrangement.trees[(block.name, tree.key)].letter
    opened = []

    async def run():
        app = GroveApp(lambda: grove, 60.0, None, flips=flip.Flip("f", hold=False))
        monkeypatch.setattr(
            app,
            "open_url",
            lambda url: opened.append((url, threading.current_thread() is threading.main_thread())),
        )
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press(*(["2", "f"] if view == "flipped" else ["tab", "2", letter]))
            await pilot.pause()
            grove_map = app.screen.query_one(GroveMap)
            x, y = next(
                (x, y)
                for y, row in enumerate(grove_map.picture.rows)
                for x, cell in enumerate(row)
                if cell.link == URL
            )
            await pilot.mouse_down(GroveMap, offset=(x, y))
            assert app.screen._drag is None
            await pilot.mouse_up(GroveMap, offset=(x, y))
            await pilot.click(GroveMap, offset=(x, y))
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.return_value is None
            assert app.screen._where.block == "2"
            assert app.screen._where.selecting == (view == "card")
            # The surrounding row keeps its existing tree-click behavior.
            x, y = next(
                (x, y)
                for y, row in enumerate(grove_map.picture.rows)
                for x, cell in enumerate(row)
                if cell.target == ("2", letter) and not cell.link
            )
            await pilot.click(GroveMap, offset=(x, y))
            await pilot.pause()
            if view == "card":
                assert app.screen._where.selected_lemon == lemon.channel
            else:
                assert app.return_value == lemon.channel

    asyncio.run(run())
    assert opened == [(URL, False)]
