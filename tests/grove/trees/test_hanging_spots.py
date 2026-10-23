from lemonaid.grove.draw import hanging


def _crown(rows: range) -> list[tuple[int, int]]:
    return [(x, y) for x in range(10, 22) for y in rows]


def _apart_on_a_row(spots) -> bool:
    return any(
        a[1] == b[1] and abs(a[0] - b[0]) > 1 for i, a in enumerate(spots) for b in spots[i + 1 :]
    )


def test_lemons_take_a_row_each_while_rows_last():
    spots = hanging.spots(_crown(range(3, 9)), (16.0, 6.0), (6.0, 3.0), 4, seed=3)
    assert len({y for _, y in spots}) == 4


def test_with_too_few_rows_lemons_bunch_instead_of_making_eyes():
    spots = hanging.spots(_crown(range(5, 7)), (16.0, 6.0), (6.0, 1.0), 4, seed=3)
    assert len(spots) == 4
    assert not _apart_on_a_row(spots)


def test_a_lemon_keeps_its_place_on_the_crown_at_any_size():
    small = hanging.spots(_crown(range(4, 9)), (16.0, 6.0), (5.0, 2.0), 3, seed=8)
    big = hanging.spots(
        [(x, y) for x in range(20, 44) for y in range(6, 18)], (32.0, 12.0), (10.0, 4.0), 3, seed=8
    )
    for (sx, _), (bx, _) in zip(small, big, strict=True):
        assert (sx < 16) == (bx < 32)
    assert [y for _, y in small] == sorted(y for _, y in small)
    assert [y for _, y in big] == sorted(y for _, y in big)


def test_no_lemon_hangs_over_the_trunk():
    spots = hanging.spots(_crown(range(3, 9)), (16.0, 6.0), (6.0, 3.0), 5, seed=3)
    assert not any(x == 16 and y >= 6 for x, y in spots)
