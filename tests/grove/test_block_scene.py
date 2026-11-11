from lemonaid.grove.draw import block_scene, canvas, colors, lemon_list
from lemonaid.grove.layout import arrange

from .shared import NOW, block, lemon, tree


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
        assert title.startswith(f" {st.letter}  {st.label} ") and key in title
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
