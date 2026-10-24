from lemonaid.grove.layout import placement


def test_a_plot_is_wider_than_tall_and_never_tiny():
    w, h = placement.plot_size(0, (0, 0))
    assert w >= 28 and h >= 9 and w > h


def test_more_trees_get_more_ground():
    small, large = placement.plot_size(300, (0, 0)), placement.plot_size(3000, (0, 0))
    assert large[0] * large[1] > small[0] * small[1]


def test_a_plot_has_room_for_its_largest_tree():
    w, h = placement.plot_size(0, (40, 20))
    assert w >= 46 and h >= 24
