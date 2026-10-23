from lemonaid.grove.layout import placement


def test_a_plot_is_wider_than_tall_and_never_tiny():
    w, h = placement.plot_size(0)
    assert w >= 28 and h >= 9 and w > h


def test_more_trees_get_more_ground():
    small, large = placement.plot_size(300), placement.plot_size(3000)
    assert large[0] * large[1] > small[0] * small[1]
