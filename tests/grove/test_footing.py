import copy
import dataclasses

from lemonaid.grove.layout import edit, footing
from lemonaid.grove.model import Plot
from lemonaid.grove.tui import drop, garden

from .shared import tree
from .test_frame import GROVE

_PLOT = Plot(0, 0, 40, 16, 6.0, 1, "rows")
_TREE = tree("t")


def test_a_tree_stands_inside_its_block_and_each_way_off_it_is_named():
    assert footing.refusal(_TREE, _PLOT, 20, 8) == ""
    assert (
        footing.refusal(_TREE, _PLOT, 20, 15) == "its tag would hang below the block's bottom edge"
    )
    assert footing.refusal(_TREE, _PLOT, 2, 8) == "its crown would reach past the block's left edge"
    assert (
        footing.refusal(_TREE, _PLOT, 38, 8) == "its crown would reach past the block's right edge"
    )
    assert footing.refusal(_TREE, _PLOT, 60, 8) == "its trunk would be off the block"


def test_a_spot_a_tree_may_stand_in_never_spills():
    for x in range(_PLOT.w + 1):
        for y in range(_PLOT.h + 1):
            if not footing.refusal(_TREE, _PLOT, x, y):
                assert not footing.spills(_TREE, _PLOT, x, y), (x, y)


def test_a_tree_dropped_wherever_its_drag_is_allowed_stays_there():
    for block in GROVE.blocks:
        plot = GROVE.arrangement.plots[block.name]
        if plot.texture == "house":
            continue

        for t in block.trees:
            at = GROVE.arrangement.trees[(block.name, t.key)]
            for x in range(0, plot.w + 1, 2):
                for y in range(plot.h + 1):
                    drag = garden.Drag(
                        block, t.key, frozenset(), (0, 0), (1.0, 1.0), moved=(x - at.cx, y - at.cy)
                    )
                    if drop.refused(GROVE, drag):
                        continue

                    try:
                        drop.drop(GROVE, drag)(copy.deepcopy(GROVE.saved))
                    except edit.EditError as error:
                        raise AssertionError((block.name, t.key, x, y, str(error))) from error


def test_a_tree_by_its_blocks_bottom_edge_is_kept_though_its_cautious_footprint_reaches_past():
    block = GROVE.blocks[0]
    t = next(t for t in block.trees if not t.lead)
    plot = GROVE.arrangement.plots[block.name]
    at = GROVE.arrangement.trees[(block.name, t.key)]
    lowest = max(
        y
        for y in range(plot.h + 1)
        if not drop.refused(
            GROVE,
            garden.Drag(block, t.key, frozenset(), (0, 0), (1.0, 1.0), moved=(0, y - at.cy)),
        )
    )
    spot = GROVE.saved["trees"][block.name][t.key]
    assert lowest - spot["top"] + spot["h"] > plot.h  # the footprint it was placed with spills

    drag = dataclasses.replace(
        garden.Drag(block, t.key, frozenset(), (0, 0), (1.0, 1.0)), moved=(0, lowest - at.cy)
    )
    changed = drop.drop(GROVE, drag)(copy.deepcopy(GROVE.saved))
    assert (changed["trees"][block.name][t.key]["y"]) == lowest
