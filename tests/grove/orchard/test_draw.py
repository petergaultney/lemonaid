from lemonaid.grove.draw import block_scene, canvas, scenes
from lemonaid.grove.layout import arrange, orchard
from lemonaid.grove.source import lemon_trees

from ..shared import NOW, block, lemon, tree

FOUND = lemon_trees.one_per_lemon(
    (block("mops", "6", tree("lead", lead=True), tree("work", lemon("a:1"), lemon("b:2"))),)
)
LAID_OUT, _ = arrange.arrange(FOUND, orchard.with_scale({"plots": {}, "trees": {}}, True), NOW)


def _text(picture: canvas.Canvas) -> str:
    return "\n".join("".join(cell.char for cell in row) for row in picture.rows)


def test_the_grove_view_draws_a_group_as_one_tree_with_a_row_and_a_key_for_each_lemon():
    picture = canvas.blank(120, 40)
    scenes.overview(picture, FOUND, LAID_OUT, 0.0)

    drawn = _text(picture)
    assert "6 MOPS" in drawn
    for t in FOUND[0].trees:
        letter = LAID_OUT.trees[("mops", t.key)].letter
        assert any(cell.target == ("6", letter) for row in picture.rows for cell in row), letter


def test_a_zoomed_group_lists_each_lemon_under_its_own_letter():
    picture = canvas.blank(160, 40)
    rows = block_scene.zoomed(picture, FOUND[0], LAID_OUT, 0.0)

    assert set(rows) == {t.key for t in FOUND[0].trees}
    for t in FOUND[0].trees:
        x, y, w, _ = rows[t.key]
        assert picture.rows[y][x + 2].target == ("6", LAID_OUT.trees[("mops", t.key)].letter)
