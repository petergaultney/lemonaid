import dataclasses

import pytest

from lemonaid.grove.draw import block_scene, canvas, ground
from lemonaid.grove.layout import arrange, edit
from lemonaid.grove.tui import drop, garden, keys
from lemonaid.grove.tui.frame import Grove

from .shared import NOW, block, tree

_SIZE = (160, 48)
_LIVE = (block("g", "1", *(tree(f"tree-{i}") for i in range(4))),)


def _grove_from(saved: dict) -> tuple[Grove, dict]:
    """The block laid out from *saved*, whose tree "going" went a minute ago, leaving a bare tree."""
    with_it = (dataclasses.replace(_LIVE[0], trees=(*_LIVE[0].trees, tree("going"))),)
    _, saved = arrange.arrange(with_it, saved, NOW)
    arrangement, saved = arrange.arrange(_LIVE, saved, NOW + 60)
    return Grove(_LIVE, arrangement, saved), saved


def _grove() -> tuple[Grove, dict]:
    return _grove_from({"plots": {}, "trees": {}})


def _grab(grove: Grove) -> garden.Drag:
    drag = garden.grab(grove, keys.Where(block="1"), _SIZE, (10, 10), ("1", "", "going"))
    assert drag and drag.stump and drag.tree == "going"
    return drag


def test_a_zoomed_block_marks_its_bare_trees_for_a_drag():
    grove, _ = _grove()
    picture = canvas.blank(*_SIZE)
    block_scene.zoomed(picture, _LIVE[0], grove.arrangement, 0.0)
    assert any(cell.target == ("1", "", "going") for row in picture.rows for cell in row)


def test_a_bare_tree_dropped_on_open_ground_stays_there():
    grove, saved = _grove()
    drag = _grab(grove)
    plot = grove.arrangement.plots["g"]
    was = grove.arrangement.stumps["g"][0]
    kept = 0
    for moved in ((dx, dy) for dx in range(-30, 31, 3) for dy in range(-6, 7, 2)):
        moving = dataclasses.replace(drag, moved=moved)
        aim = (was.cx + moved[0], was.cy + moved[1])
        if not ground.inside(plot, plot.x + aim[0], plot.y + aim[1]) or drop.refused(grove, moving):
            continue
        again = arrange.arrange(_LIVE, drop.drop(grove, moving, NOW + 60)(saved), NOW + 60)[0]
        assert [(s.key, s.cx, s.cy) for s in again.stumps["g"]] == [("going", *aim)]
        kept += 1
    assert kept


def test_a_bare_tree_onto_a_tree_is_refused():
    grove, _ = _grove()
    was = grove.arrangement.stumps["g"][0]
    at = grove.arrangement.trees[("g", "tree-0")]
    onto = dataclasses.replace(_grab(grove), moved=(at.cx - was.cx, at.cy - was.cy))
    assert drop.refused(grove, onto) == "a tree stands there"
    assert "a tree stands there" in drop.describe(grove, onto)


def test_a_bare_tree_dragged_off_its_block_is_cleared():
    grove, saved = _grove()
    away = dataclasses.replace(_grab(grove), moved=(1000, 0))
    assert drop.refused(grove, away) == ""
    assert drop.describe(grove, away).startswith("clearing bare tree going")
    assert drop.dragged(grove, away).arrangement.stumps["g"] == ()

    cleared = drop.drop(grove, away, NOW + 60)(saved)
    assert "going" not in cleared["trees"]["g"]
    assert arrange.arrange(_LIVE, cleared, NOW + 60)[0].stumps["g"] == ()


def test_a_bare_tree_whose_tree_came_back_is_not_dropped():
    grove, saved = _grove()
    away = dataclasses.replace(_grab(grove), moved=(1000, 0))
    back = (dataclasses.replace(_LIVE[0], trees=(*_LIVE[0].trees, tree("going"))),)
    _, saved = arrange.arrange(back, saved, NOW + 120)
    with pytest.raises(edit.EditError, match="No bare tree"):
        drop.drop(grove, away, NOW + 120)(saved)


def test_a_bare_tree_is_not_dropped_on_a_tree_that_arrived_during_the_drag():
    with_both = (
        dataclasses.replace(_LIVE[0], trees=(*_LIVE[0].trees, tree("older"), tree("going"))),
    )
    _, saved = arrange.arrange(with_both, {"plots": {}, "trees": {}}, NOW - 60)
    grove, saved = _grove_from(saved)
    newer = (dataclasses.replace(_LIVE[0], trees=(*_LIVE[0].trees, tree("newcomer"))),)
    fresh, saved = arrange.arrange(newer, saved, NOW + 90)  # it takes "older"'s spot
    at = fresh.trees[("g", "newcomer")]
    was = next(s for s in grove.arrangement.stumps["g"] if s.key == "going")
    onto = dataclasses.replace(_grab(grove), moved=(at.cx - was.cx, at.cy - was.cy))
    assert drop.refused(grove, onto) == ""
    with pytest.raises(edit.EditError, match="changed while you dragged"):
        drop.drop(grove, onto, NOW + 90)(saved)


def test_a_bare_tree_is_not_dropped_off_ground_its_block_lost_during_the_drag():
    grove, saved = _grove()
    plot, was = grove.arrangement.plots["g"], grove.arrangement.stumps["g"][0]
    saved = edit.reshape(saved, "g", 1.5)
    after = arrange.arrange(_LIVE, saved, NOW + 60)[0].plots["g"]
    lost = [
        dataclasses.replace(_grab(grove), moved=(x - was.cx, y - was.cy))
        for x in range(plot.w)
        for y in range(plot.h)
        if ground.inside(plot, plot.x + x, plot.y + y)
        and not ground.inside(after, after.x + x, after.y + y)
    ]
    drags = [d for d in lost if not drop.refused(grove, d)]
    assert drags
    with pytest.raises(edit.EditError, match="block changed while you dragged"):
        drop.drop(grove, drags[0], NOW + 60)(saved)
