from lemonaid.grove.draw import block_scene, canvas, lemon_list, trees
from lemonaid.grove.layout import arrange

from .shared import NOW, block, lemon, tree

SHAPE = trees.shape(tree("t"), "t", 1.0)
FOOTPRINT = (90, 25, 20, 8)  # a tree and its tag, standing at column 100


def _spot(taken: list[block_scene.Rect]) -> block_scene.Rect:
    x, y = block_scene._list_spot(canvas.blank(200, 60), 100.0, FOOTPRINT, 4, [FOOTPRINT, *taken])
    return x, y, lemon_list.WIDTH, 4


def _touches_its_tree(spot: block_scene.Rect) -> bool:
    x, y, w, h = spot
    fx, fy, fw, fh = FOOTPRINT
    spans_trunk = x < 100 < x + w
    return (spans_trunk and (y == fy + fh + 1 or y + h + 1 == fy)) or (
        fy <= y <= fy + fh and (x == fx + fw + 2 or x + w + 2 == fx)
    )


def test_a_list_goes_under_its_tree_when_there_is_room():
    x, y, w, _ = _spot([])
    assert y == FOOTPRINT[1] + FOOTPRINT[3] + 1 and x < 100 < x + w


def test_a_list_blocked_below_goes_above_or_beside_but_stays_by_its_tree():
    below = [(0, FOOTPRINT[1] + FOOTPRINT[3], 200, 10)]
    spot = _spot(below)
    assert _touches_its_tree(spot)
    assert block_scene._overlap(spot, below) == 0


def test_a_hemmed_in_list_still_stays_by_its_tree():
    hemmed = [(0, 0, 200, FOOTPRINT[1] - 1), (0, FOOTPRINT[1] + FOOTPRINT[3], 200, 30)]
    assert _touches_its_tree(_spot(hemmed))


def test_a_list_too_tall_for_the_screen_comes_back_on_it_once_it_fits():
    big = block("g", "1", tree("t", *(lemon(f"claude:{i}") for i in range(45))))
    arrangement, _ = arrange.arrange((big,), {"plots": {}, "trees": {}}, NOW)
    lists: dict = {}
    block_scene.zoomed(canvas.blank(120, 40), big, arrangement, 0.0, lists=lists)
    small = block("g", "1", tree("t", lemon("claude:0")))
    block_scene.zoomed(canvas.blank(120, 40), small, arrangement, 0.0, lists=lists)
    x, y, _ = lists["t"]
    assert 1 <= x <= 119 - lemon_list.WIDTH and 1 <= y <= 36
