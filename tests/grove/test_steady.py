"""Lemons coming and going on one tree move nothing else in its block."""

from lemonaid.grove.draw import block_scene, canvas
from lemonaid.grove.layout import arrange

from .shared import NOW, block, lemon, tree


def _where_things_are(found, saved, now, lists):
    """Each tree's drawn cells in the zoomed block, by letter, and the saved layout."""
    arrangement, saved = arrange.arrange((found,), saved, now)
    picture = canvas.blank(200, 60)
    block_scene.zoomed(picture, found, arrangement, 0.5, lists=lists)
    cells: dict[str, set[tuple[int, int]]] = {}
    for y, row in enumerate(picture.rows):
        for x, cell in enumerate(row):
            if len(cell.target) == 2:
                cells.setdefault(cell.target[1], set()).add((x, y))
    letters = {t.key: arrangement.trees[(found.name, t.key)].letter for t in found.trees}
    return {key: cells[letter] for key, letter in letters.items()}, saved


def test_lemons_closing_on_one_tree_move_no_other_tree_tag_or_list():
    busy = tree("busy", *(lemon(f"claude:b{i}") for i in range(6)))
    others = [tree(name) for name in ("alpha", "bravo", "charlie", "delta")]
    lists: dict = {}  # as a grove that stays open remembers them
    first = block("g", "1", busy, *others)
    before, saved = _where_things_are(first, {"plots": {}, "trees": {}}, NOW, lists)
    quiet = tree("busy", lemon("claude:b0"))
    after, saved = _where_things_are(block("g", "1", quiet, *others), saved, NOW + 60, lists)
    again, _ = _where_things_are(block("g", "1", busy, *others), saved, NOW + 120, lists)
    for t in others:
        assert after[t.key] == before[t.key], t.key
        assert again[t.key] == before[t.key], t.key
