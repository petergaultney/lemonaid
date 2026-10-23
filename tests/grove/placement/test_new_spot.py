from lemonaid.grove.layout import placement
from lemonaid.grove.model import Plot

PLOT = Plot(0, 0, 80, 24, roundness=4.5, seed=7, texture="rows")


def test_a_spot_stays_inside_the_plot():
    x, y = placement.new_spot(PLOT, (14, 7), [])
    assert x >= 1 and x + 14 <= PLOT.w - 1 and y >= 1 and y + 7 <= PLOT.h - 1


def test_a_spot_aimed_at_a_point_stands_as_near_it_as_fits():
    x, _ = placement.new_spot(PLOT, (14, 7), [], toward=(PLOT.w, PLOT.h / 2))
    assert x + 14 > PLOT.w * 0.75


def test_a_new_tree_does_not_cover_one_already_standing():
    first = (*placement.new_spot(PLOT, (14, 7), []), 14, 7)
    second = (*placement.new_spot(PLOT, (14, 7), [first]), 14, 7)
    assert not placement.overlaps(first, second, 0)


def test_a_full_plot_spills_the_tree_just_past_its_edge_instead_of_covering_one():
    crowded = [(0, 0, PLOT.w, PLOT.h), (PLOT.w + 2, 3, 10, 7)]
    x, y = placement.new_spot(PLOT, (14, 7), crowded)
    assert not any(placement.overlaps((x, y, 14, 7), other, 0) for other in crowded)
    assert -7 <= y <= 1 or PLOT.h - 1 <= y <= PLOT.h + 1  # hugging the top or bottom edge
