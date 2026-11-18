import copy

from lemonaid.grove.draw import block_scene, canvas, colors, lemon_list
from lemonaid.grove.layout import arrange
from lemonaid.grove.tui import drop, frame, garden, keys

from .shared import NOW, block, lemon, tree

_SIZE = (200, 64)


def test_each_list_is_titled_with_its_trees_tag_then_its_place_key_muted():
    grove = block(
        "g", "1", tree("tars/one"), tree("tars/two", lemon("claude:a"), lemon("claude:b"))
    )
    arrangement, _ = arrange.arrange((grove,), {"plots": {}, "trees": {}}, NOW)
    c = canvas.blank(160, 45)
    spots = block_scene.zoomed(c, grove, arrangement, 0.0, lists={})
    for key, (x, y, w, _) in spots.items():
        st = arrangement.trees[("g", key)]
        title = "".join(cell.char for cell in c.rows[y][x + 1 : x + w - 1])
        assert f" {st.letter}  {st.label} " in title and key in title
        at = x + 1 + title.index(key)
        assert c.rows[y][at].fg == colors.MUTED and c.rows[y][at].target == ("1", st.letter)


def test_a_list_too_tall_for_the_screen_comes_back_on_it_once_it_fits():
    big = block("g", "1", tree("t", *(lemon(f"claude:{i}") for i in range(45))))
    arrangement, _ = arrange.arrange((big,), {"plots": {}, "trees": {}}, NOW)
    lists: dict = {}
    block_scene.zoomed(canvas.blank(120, 40), big, arrangement, 0.0, lists=lists)
    small = block("g", "1", tree("t", lemon("claude:0")))
    block_scene.zoomed(canvas.blank(120, 40), small, arrangement, 0.0, lists=lists)
    x, y, _ = lists["t"]
    assert 1 <= x <= 119 - lemon_list.WIDTH and 1 <= y <= 36


def test_a_list_clamped_away_from_its_tree_leaves_no_second_copy_of_the_title():
    grove = block(
        "g",
        "1",
        tree("inbox/brief-first", lemon("claude:a")),
        tree("tars/two", lemon("claude:b"), lemon("claude:c")),
    )
    arrangement, _ = arrange.arrange((grove,), {"plots": {}, "trees": {}}, NOW)
    c = canvas.blank(60, 14)
    block_scene.zoomed(c, grove, arrangement, 0.0, lists={})
    screen = ["".join(cell.char for cell in row) for row in c.rows]
    for st in arrangement.trees.values():
        assert sum(row.count(f" {st.letter}  {st.label} ") for row in screen) == 1


def test_a_list_that_cannot_hang_from_its_tag_is_reported_astray():
    grove = block(
        "g",
        "1",
        tree("inbox/brief-first", lemon("claude:a")),
        tree("tars/two", lemon("claude:b"), lemon("claude:c")),
    )
    arrangement, _ = arrange.arrange((grove,), {"plots": {}, "trees": {}}, NOW)
    roomy: list[str] = []
    cramped: list[str] = []

    block_scene.zoomed(canvas.blank(200, 60), grove, arrangement, 0.0, lists={}, astray=roomy)
    block_scene.zoomed(canvas.blank(60, 14), grove, arrangement, 0.0, lists={}, astray=cramped)

    assert roomy == []
    assert cramped


def test_a_dropped_trees_list_moves_no_other_list_on_the_next_frame():
    grove = block("g", "1", tree("t0"), tree("t1"), tree("t2"))
    arrangement, saved = arrange.arrange((grove,), {"plots": {}, "trees": {}}, NOW)
    shown = frame.Grove((grove,), arrangement, saved)
    at = arrangement.trees[("g", "t0")]
    drag = garden.Drag(grove, "t0", frozenset(), (0, 0), (1.0, 1.0), moved=(6 - at.cx, 1 - at.cy))
    assert not drop.refused(shown, drag)

    where = keys.Where(block="1")
    lists: frame.Lists = {}
    frame.render(shown, where, *_SIZE, 0.0, lists=lists)
    for spots in lists.values():  # as the screen does on a drop
        spots.pop("t0", None)
    dropped = drop.dragged(shown, drag)
    frame.render(dropped, where, *_SIZE, 0.0, lists=lists)
    first = copy.deepcopy(lists)
    frame.render(dropped, where, *_SIZE, 0.0, lists=lists)
    assert lists == first
