from lemonaid.grove.draw import crown

# A clump on top of two, with a gap between the two for the trunk.
_BLOBS = ((0.0, -1.0, 6.0, 2.0, 1.0), (-3.5, 0.8, 3.0, 1.5, 0.5), (3.5, 0.8, 3.0, 1.5, 0.5))


def _cells() -> dict[tuple[int, int], tuple[str, int, int]]:
    return {
        (x, y): (char, drawn, back)
        for x, y, char, drawn, back in crown.cells(_BLOBS, (20.0, 10.0), (0, 0, 40, 30), 20)
    }


def _leaves(cells, row: int) -> set[int]:
    return {
        paint
        for (_, y), (_, drawn, back) in cells.items()
        if y == row
        for paint in (drawn, back)
        if crown.NONE != paint < crown.BARK
    }


def test_the_crown_is_lit_on_top_and_shaded_underneath():
    cells = _cells()
    top, bottom = min(y for _, y in cells), max(y for _, y in cells)
    assert 3 in _leaves(cells, top) | _leaves(cells, top + 1)
    assert 0 in _leaves(cells, bottom)
    assert 3 not in _leaves(cells, bottom)


def test_the_trunk_shows_between_the_bottom_clumps_and_no_lower():
    cells = _cells()
    bottom = max(y for _, y in cells)
    bark = {(x, y) for (x, y), (_, drawn, back) in cells.items() if crown.BARK in (drawn, back)}
    assert {x for x, _ in bark} <= {19, 20, 21}
    assert any(y < bottom for _, y in bark)
    assert all(y <= bottom for _, y in bark)


def test_a_bare_trees_bark_is_lit_left_of_its_trunk_and_shaded_right():
    cells = {
        (x, y): (drawn, back) for x, y, _, drawn, back in crown.bare(("▝▙ █ ▟▘", "   █   "), 3.5)
    }
    assert cells[(0, 0)] == cells[(1, 0)] == (crown.BARK, crown.NONE)
    assert cells[(5, 0)] == cells[(6, 0)] == (crown.BARK_SHADE, crown.NONE)
    assert set(cells[(3, 1)]) == {crown.BARK, crown.BARK_SHADE}
