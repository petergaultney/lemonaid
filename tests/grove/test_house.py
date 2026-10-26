import dataclasses

from lemonaid.grove.draw import canvas, house
from lemonaid.grove.draw.plots import View
from lemonaid.grove.layout import arrange

from .shared import NOW, block, lemon, tree


def _bay_b(packhouse, saved, now, zoomed: bool):
    """Where tree b's bay starts, and the layout saved after drawing it."""
    found, saved = arrange.arrange((packhouse,), saved, now)
    picture = canvas.blank(200, 60)
    if zoomed:
        house.zoomed(picture, packhouse, found, 0.0, None, "")
    else:
        house.draw(picture, packhouse, found, View(0, 0, 1.0, 1.0), 0.0, lambda _: 0.0)
    target = ("0", found.trees[("", "b")].letter)
    first = next(
        (x, y)
        for y, row in enumerate(picture.rows)
        for x, cell in enumerate(row)
        if cell.target == target
    )
    return first, saved


def test_a_bay_keeps_its_place_when_an_earlier_session_leaves():
    for zoomed in (False, True):
        before, saved = _bay_b(
            block("", "0", tree("a"), tree("b")), {"plots": {}, "trees": {}}, NOW, zoomed
        )
        after, _ = _bay_b(block("", "0", tree("b")), saved, NOW + 60, zoomed)
        assert before == after, zoomed


def test_bays_keep_their_rows_when_the_largest_session_leaves():
    big = tree("a", *(lemon(f"claude:a{i}") for i in range(9)))
    for zoomed in (False, True):
        before, saved = _bay_b(
            block("", "0", big, tree("b"), tree("c")), {"plots": {}, "trees": {}}, NOW, zoomed
        )
        after, _ = _bay_b(block("", "0", tree("b"), tree("c")), saved, NOW + 60, zoomed)
        assert before == after, zoomed


def test_a_new_session_takes_a_free_bay_and_moves_no_other():
    for zoomed in (False, True):
        before, saved = _bay_b(block("", "0", tree("b")), {"plots": {}, "trees": {}}, NOW, zoomed)
        after, _ = _bay_b(block("", "0", tree("a"), tree("b")), saved, NOW + 60, zoomed)
        assert before == after, zoomed


def test_a_big_session_lists_five_rows_ending_with_how_many_more():
    big = tree("b", *(lemon(f"claude:b{i}") for i in range(9)))
    found, _ = arrange.arrange((block("", "0", big),), {"plots": {}, "trees": {}}, NOW)
    picture = canvas.blank(200, 60)
    house.zoomed(picture, block("", "0", big), found, 0.0, None, "")
    shown = "\n".join(canvas.plain_lines(picture))
    assert "+5 more" in shown and "claude:b4" not in shown


def test_bays_keep_their_rows_on_a_small_screen_when_the_last_bay_leaves():
    sessions = [tree(k, *(lemon(f"claude:{k}{i}") for i in range(3))) for k in "abcdef"]

    def where_b(packhouse, saved, now):
        found, saved = arrange.arrange((packhouse,), saved, now)
        picture = canvas.blank(120, 40)
        house.zoomed(picture, packhouse, found, 0.0, None, "")
        target = ("0", found.trees[("", "b")].letter)
        return next(
            (x, y)
            for y, row in enumerate(picture.rows)
            for x, c in enumerate(row)
            if c.target == target
        ), saved

    before, saved = where_b(block("", "0", *sessions), {"plots": {}, "trees": {}}, NOW)
    after, _ = where_b(block("", "0", *sessions[:-1]), saved, NOW + 60)
    assert before == after


def test_a_bay_shows_its_main_lemons_emoji_after_its_key_and_its_pin_before_it():
    packhouse = block(
        "", "0", tree("b", dataclasses.replace(lemon("claude:b"), emoji="🌎", pinned=True))
    )
    found, _ = arrange.arrange((packhouse,), {"plots": {}, "trees": {}}, NOW)
    picture = canvas.blank(200, 60)
    house.draw(picture, packhouse, found, View(0, 0, 1.0, 1.0), 0.0, lambda _: 0.0)
    assert any("▐ 0b  🌎 b" in line for line in canvas.plain_lines(picture))
