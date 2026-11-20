import math

from lemonaid.grove.model import Plot
from lemonaid.grove.window import roads

EAST_WEST = [[0, 20], [40, 19], [80, 20], [116, 19]]
NORTH_SOUTH = [[122, 0], [120, 12], [118, 24], [113, 28], [108, 32]]
BELOW_HOUSE = [[108, 35], [106, 40], [104, 46], [104, 72]]
HOUSE = Plot(96, 28, 24, 13, 4.5, 3, "house")


def test_an_end_on_the_border_runs_far_past_it_and_one_short_of_a_road_meets_it():
    east_west, north_south, below = roads.drawn([EAST_WEST, NORTH_SOUTH, BELOW_HOUSE], [HOUSE])

    assert east_west[0][0] < -300  # off the left edge, well past any view
    assert north_south[0][1] < -300  # off the top
    assert below[-1][1] > 60 + 300  # off the bottom
    tee = east_west[-1]
    assert math.dist(tee, (116, 19)) < 8
    assert abs(tee[0] - (120 + (118 - 120) * (tee[1] - 12) / 12)) < 0.01  # on the north-south road


def test_ends_inside_the_packhouse_and_ends_far_from_any_road_are_left_where_they_are():
    _east_west, north_south, below = roads.drawn([EAST_WEST, NORTH_SOUTH, BELOW_HOUSE], [HOUSE])
    alone = roads.drawn([[[50, 10], [60, 10]], [[100, 50], [100, 55]]], [])

    assert north_south[-1] == (108, 32) and below[0] == (108, 35)
    assert alone == [[(50, 10), (60, 10)], [(100, 50), (100, 55)]]
