from lemonaid.grove.layout import placement
from lemonaid.grove.model import Plot

PLOT = Plot(0, 0, 80, 24, roundness=4.5, seed=7, texture="rows")


def test_a_spot_stays_inside_the_plot():
    x, y = placement.new_spot(PLOT, [(14, 7, 0)], [])[0]
    assert x >= 1 and x + 14 <= PLOT.w - 1 and y >= 1 and y + 7 <= PLOT.h - 1


def test_a_spot_aimed_at_a_point_stands_as_near_it_as_fits():
    x, _ = placement.new_spot(PLOT, [(14, 7, 0)], [], toward=(PLOT.w, PLOT.h / 2))[0]
    assert x + 14 > PLOT.w * 0.75


def test_a_new_tree_does_not_cover_one_already_standing():
    first = (*placement.new_spot(PLOT, [(14, 7, 0)], [])[0], 14, 7)
    second = (*placement.new_spot(PLOT, [(14, 7, 0)], [first])[0], 14, 7)
    assert not placement.overlaps(first, second, 0)


def test_a_full_plot_spills_the_tree_just_past_its_edge_instead_of_covering_one():
    crowded = [(0, 0, PLOT.w, PLOT.h), (PLOT.w + 2, 3, 10, 7)]
    (x, y), _ = placement.new_spot(PLOT, [(14, 7, 0)], crowded)
    assert not any(placement.overlaps((x, y, 14, 7), other, 0) for other in crowded)
    assert -7 <= y <= 1 or PLOT.h - 1 <= y <= PLOT.h + 1  # hugging the top or bottom edge


def test_a_tree_too_big_for_the_room_left_takes_its_smaller_size_inside():
    big = (0, 0, PLOT.w, 12)  # the top half taken
    spot, size = placement.new_spot(PLOT, [(14, 14, 0), (14, 7, 0)], [big])
    assert size == (14, 7, 0) and not placement.overlaps((*spot, *size[:2]), big, 0)


def test_squeezed_into_a_full_plot_a_tree_stays_on_its_ground():
    crowded = [(0, 0, PLOT.w, PLOT.h)]
    (x, y), _ = placement.new_spot(PLOT, [(14, 7, 0)], crowded, squeeze=True)
    assert x >= 0 and x + 14 <= PLOT.w and y >= 0 and y + 7 <= PLOT.h


def test_a_crown_may_rise_above_the_plot_but_its_middle_stays_on_it():
    short = Plot(0, 0, 80, 10, roundness=12, seed=7, texture="rows")
    assert placement.first_room(short, [(14, 16, 0)], []) is None
    (_x, y), _ = placement.first_room(short, [(14, 16, 8)], [])
    assert y < 0 and y + 8 >= 1 and y + 16 <= short.h - 1
