import dataclasses

from lemonaid.grove.draw import canvas, hanging, trees

from ..shared import lemon, tree


def _decorated(label: str, emoji: str = "", pinned: bool = False):
    return dataclasses.replace(
        tree("t", dataclasses.replace(lemon("claude:t"), emoji=emoji, pinned=pinned)), label=label
    )


def test_a_sapling_shows_a_short_name_whole():
    s = trees.shape(_decorated("project templates"), "p", 0.62)
    assert len(s.tag) == 1
    assert "project" in s.tag[0]
    assert "…" not in s.tag[0]


def test_a_grown_tree_wraps_its_name_onto_two_lines():
    s = trees.shape(_decorated("spatial lemon jump"), "s", 1.0)
    assert "".join(s.tag).split() == ["s", "spatial", "lemon", "jump"]


def test_the_emoji_and_pin_get_room_after_the_name():
    plain = trees.shape(_decorated("spatial"), "s", 0.62)
    marked = trees.shape(_decorated("spatial", emoji="🌎", pinned=True), "s", 0.62)
    assert marked.width == plain.width + 4
    assert marked.tag[0].rstrip() == plain.tag[0].rstrip()


def test_even_a_small_crown_has_a_row_for_each_lemon():
    for count in range(1, 6):
        big = tree("t", *(lemon(f"claude:{i}") for i in range(count)))
        for size in (0.42, 1.0):
            s = trees.shape(big, "t", size)
            for offset in (0.0, 0.25, 0.5, 0.75):
                center = (40.3, 20.0 + offset)
                solid, _ = trees._crown(canvas.blank(80, 40), s, *center, ("#000000", "#111111"))
                spots = hanging.spots(solid, center, (s.rx, s.ry), count, seed=7)
                assert len({y for _, y in spots}) == count
