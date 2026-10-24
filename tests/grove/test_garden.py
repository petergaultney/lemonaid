import asyncio
import dataclasses

import pytest

from lemonaid.grove.draw import canvas, scene_parts
from lemonaid.grove.layout import arrange, edit, state
from lemonaid.grove.tui import drop, garden, keys
from lemonaid.grove.tui.app import GroveApp
from lemonaid.grove.tui.frame import Grove, render

from .shared import NOW, block, tree
from .test_frame import BLOCKS, GROVE

_SIZE = (160, 48)


def _screen_box(name: str) -> tuple[int, int, int, int]:
    plot = GROVE.arrangement.plots[name]
    view = scene_parts.grove_view(_SIZE, GROVE.arrangement)
    x0, y0 = view.screen(plot.x, plot.y)
    x1, y1 = view.screen(plot.x + plot.w, plot.y + plot.h)
    return round(x0), round(y0), round(x1), round(y1)


def _grab(name: str, at: tuple[int, int]) -> garden.Drag:
    digit = next(b.digit for b in GROVE.blocks if b.name == name)
    drag = garden.grab(GROVE, keys.Where(), _SIZE, at, (digit,))
    assert drag is not None
    return drag


def test_the_middle_of_a_block_moves_it_and_its_edge_resizes_it():
    x0, y0, x1, y1 = _screen_box("oria")
    middle = _grab("oria", ((x0 + x1) // 2, (y0 + y1) // 2))
    edge = _grab("oria", (x1 - 1, (y0 + y1) // 2))
    assert middle.sides == frozenset() and edge.sides == {"right"}

    plot = GROVE.arrangement.plots["oria"]
    wider = drop.dragged(GROVE, dataclasses.replace(edge, moved=(4, 0))).arrangement
    assert wider.plots["oria"] == dataclasses.replace(plot, w=plot.w + 4)


def test_a_block_dropped_on_another_is_refused():
    oria, relay = GROVE.arrangement.plots["oria"], GROVE.arrangement.plots["relay"]
    drag = dataclasses.replace(
        _grab("oria", (0, 0)), sides=frozenset(), moved=(relay.x - oria.x, relay.y - oria.y)
    )
    assert drop.refused(GROVE, drag) == "another block's ground is there"


def test_a_tree_moves_inside_its_block_but_not_out_of_it_or_onto_another():
    block = GROVE.blocks[0]
    tree = block.trees[1]
    letter = GROVE.arrangement.trees[(block.name, tree.key)].letter
    view = scene_parts.block_view(canvas.blank(*_SIZE), GROVE.arrangement, block)
    drag = garden.grab(GROVE, keys.Where(block="1"), _SIZE, (10, 10), ("1", letter))
    assert drag and drag.tree == tree.key and drag.scale == (view.sx, view.sy)

    at = GROVE.arrangement.trees[(block.name, tree.key)]
    lead = GROVE.arrangement.trees[(block.name, block.trees[0].key)]
    onto = dataclasses.replace(drag, moved=(lead.cx - at.cx, lead.cy - at.cy))
    assert drop.refused(GROVE, onto) == "another tree stands there"
    away = dataclasses.replace(drag, moved=(1000, 0))
    assert drop.refused(GROVE, away) == "a tree stays on its block's ground"


def test_dragging_a_block_saves_where_it_was_dropped():
    x0, y0, x1, y1 = _screen_box("relay")
    start = ((x0 + x1) // 2, (y0 + y1) // 2)
    before = GROVE.arrangement.plots["relay"]
    state.save({"version": 1, "plots": {"relay": dataclasses.asdict(before)}, "trees": {}})

    async def run() -> None:
        app = GroveApp(lambda: GROVE, 60.0, None)
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.mouse_down(offset=start)
            await pilot.hover(offset=(start[0], start[1] - 3))
            await pilot.mouse_up(offset=(start[0], start[1] - 3))
            await app.workers.wait_for_complete()
            await pilot.pause()

    asyncio.run(run())
    saved = state.load()["plots"]["relay"]
    assert (saved["x"], saved["y"]) != (before.x, before.y)
    assert saved["x"] == before.x and saved["y"] < before.y


def test_a_block_dragged_to_nothing_still_draws_and_is_refused():
    plot = GROVE.arrangement.plots["oria"]
    _x0, y0, x1, y1 = _screen_box("oria")
    drag = dataclasses.replace(_grab("oria", (x1 - 1, (y0 + y1) // 2)), moved=(-plot.w - 3, 0))
    render(drop.dragged(GROVE, drag), keys.Where(), *_SIZE, 0.0)
    assert drop.refused(GROVE, drag) == "a block needs at least 12 columns and 5 rows"


def test_a_dropped_tree_stays_where_it_was_dropped_or_is_refused():
    blocks = (block("sample", "1", *(tree(f"tree-{i}") for i in range(6))),)
    arrangement, saved = arrange.arrange(blocks, {"plots": {}, "trees": {}}, NOW)
    grove = Grove(blocks, arrangement)
    at = arrangement.trees[("sample", "tree-1")]
    drag = garden.grab(grove, keys.Where(block="1"), _SIZE, (10, 10), ("1", at.letter))
    assert drag is not None
    kept = 0
    for moved in [
        (16 - at.cx, 8 - at.cy),
        *((dx, dy) for dx in range(-24, 25, 3) for dy in (-3, 0, 3)),
    ]:
        try:
            changed = drop.drop(grove, dataclasses.replace(drag, moved=moved), NOW)(saved)
        except edit.EditError:
            continue
        again = arrange.arrange(blocks, changed, NOW)[0].trees[("sample", "tree-1")]
        assert (again.cx, again.cy) == (at.cx + moved[0], at.cy + moved[1]), moved
        kept += 1
    assert kept


def test_a_drop_checks_the_saved_layout_not_the_one_it_was_dragged_on():
    arrangement, saved = arrange.arrange(BLOCKS, {"plots": {}, "trees": {}}, NOW)
    old = Grove(BLOCKS, arrangement)
    drag = dataclasses.replace(_grab("relay", (0, 0)), sides=frozenset(), moved=(100, 0))
    assert drop.refused(old, drag) == ""

    state.save(saved)
    relay = arrangement.plots["relay"]
    state.update(lambda s: edit.move(s, "oria", relay.x + 100, relay.y))
    with pytest.raises(edit.EditError, match="another block's ground"):
        state.update(drop.drop(old, drag, NOW))
    assert state.load()["plots"]["relay"]["x"] == relay.x


def test_a_drop_is_refused_when_a_tree_arrived_in_its_block_during_the_drag():
    arrangement, saved = arrange.arrange(BLOCKS, {"plots": {}, "trees": {}}, NOW)
    old = Grove(BLOCKS, arrangement)
    _x0, y0, x1, y1 = _screen_box("oria")
    drag = dataclasses.replace(_grab("oria", (x1 - 1, (y0 + y1) // 2)), moved=(-2, 0))
    assert drop.refused(old, drag) == ""

    newer = (dataclasses.replace(BLOCKS[0], trees=(*BLOCKS[0].trees, tree("new-one"))), *BLOCKS[1:])
    _, saved = arrange.arrange(newer, saved, NOW)
    width = saved["plots"]["oria"]["w"]
    with pytest.raises(edit.EditError, match="changed while you dragged"):
        drop.drop(old, drag, NOW)(saved)
    assert saved["plots"]["oria"]["w"] == width


def test_a_tree_dropped_by_its_blocks_edge_is_taken_though_its_tag_reaches_past():
    block = GROVE.blocks[0]
    tree_ = block.trees[1]
    at = GROVE.arrangement.trees[(block.name, tree_.key)]
    plot = GROVE.arrangement.plots[block.name]
    drag = garden.grab(GROVE, keys.Where(block="1"), _SIZE, (10, 10), ("1", at.letter))
    to_edge = dataclasses.replace(drag, moved=(plot.w - 4 - at.cx, plot.h // 2 - at.cy))
    assert drop.refused(GROVE, to_edge) == ""


def test_a_dropped_trees_lemon_list_is_placed_beside_it_again():
    block = GROVE.blocks[0]
    tree_ = block.trees[1]
    letter = GROVE.arrangement.trees[(block.name, tree_.key)].letter
    lists = {("1", *_SIZE): {tree_.key: (0, 0), block.trees[0].key: (5, 5)}}

    async def run() -> None:
        app = GroveApp(lambda: GROVE, 60.0, None)
        app._lists = lists
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("1")
            await pilot.pause()
            app.screen._lists = lists
            app.screen._drag = garden.grab(
                GROVE, keys.Where(block="1"), _SIZE, (10, 10), ("1", letter)
            )
            app.screen._drag = dataclasses.replace(app.screen._drag, moved=(1, 0))
            app.screen.on_mouse_up(None)
            await app.workers.wait_for_complete()

    asyncio.run(run())
    assert lists[("1", *_SIZE)].get(tree_.key) != (0, 0)


@pytest.mark.parametrize(
    ("mouse", "expected"),
    [
        ([], "1"),  # no mouse at all
        (["down"], "1"),  # a press whose release never came
        (["down", "up"], "1"),  # a click
    ],
)
def test_typing_reaches_the_grove_whatever_the_mouse_did_first(mouse, expected):
    x0, y0, x1, y1 = _screen_box("relay")
    at = ((x0 + x1) // 2, (y0 + y1) // 2)

    async def run() -> str:
        app = GroveApp(lambda: GROVE, 60.0, None)
        async with app.run_test(size=_SIZE) as pilot:
            for event in mouse:
                await (pilot.mouse_down if event == "down" else pilot.mouse_up)(offset=at)
            await pilot.press("1")
            await pilot.pause()
            return app.screen._where.block

    assert asyncio.run(run()) == expected


@pytest.mark.parametrize(
    "before",
    [[], ["down"], ["down", "up"], ["question_mark", "x"]],
    ids=["nothing", "a press never released", "a click", "the key panel"],
)
def test_every_lemons_key_typed_into_the_grove_chooses_it(before):
    names = keys.names(GROVE.blocks, GROVE.arrangement)
    x0, y0, x1, y1 = _screen_box("relay")
    on_a_block = ((x0 + x1) // 2, (y0 + y1) // 2)

    async def run(typed: str) -> list[str]:
        chosen: list[str] = []
        app = GroveApp(lambda: GROVE, 60.0, None, choose=lambda c: chosen.append(c) or "")
        async with app.run_test(size=_SIZE) as pilot:
            for step in before:
                if step == "down":
                    await pilot.mouse_down(offset=on_a_block)
                elif step == "up":
                    await pilot.mouse_up(offset=on_a_block)
                else:
                    await pilot.press(step)
            await pilot.press(*typed)
            await pilot.pause()
        return chosen

    for channel, typed in names.items():
        assert asyncio.run(run(typed)) == [channel], typed
