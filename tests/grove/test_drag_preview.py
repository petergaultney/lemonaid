import copy
import itertools

from lemonaid.grove.layout import arrange
from lemonaid.grove.tui import drop, garden

from .test_frame import GROVE


def test_a_dragged_tree_and_its_neighbors_are_drawn_at_the_sizes_dropping_it_gives():
    shrunk = 0
    for blk in GROVE.blocks:
        plot = GROVE.arrangement.plots[blk.name]
        if plot.texture == "house":
            continue

        for t in blk.trees:
            at = GROVE.arrangement.trees[(blk.name, t.key)]
            for x, y in itertools.product(range(0, plot.w + 1, 2), range(plot.h + 1)):
                drag = garden.Drag(
                    blk, t.key, frozenset(), (0, 0), (1.0, 1.0), moved=(x - at.cx, y - at.cy)
                )
                if drop.refused(GROVE, drag):
                    continue

                shown = drop.dragged(GROVE, drag).arrangement.trees
                saved = drop.drop(GROVE, drag)(copy.deepcopy(GROVE.saved))
                laid_out = arrange.arrange(GROVE.blocks, saved)[0].trees
                sizes = {k.key: laid_out[(blk.name, k.key)].size for k in blk.trees}
                assert {k.key: shown[(blk.name, k.key)].size for k in blk.trees} == sizes
                shrunk += any(sizes[k] < GROVE.arrangement.trees[(blk.name, k)].size for k in sizes)
    assert shrunk  # some drop shrinks a tree, so the sizes are what's being checked
