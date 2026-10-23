from lemonaid.grove.layout import placement
from lemonaid.grove.model import WORLD_HEIGHT, WORLD_WIDTH


def _center(rect):
    x, y, w, h = rect
    return x + w / 2, y + h / 2


def test_the_first_plot_goes_near_the_middle():
    plot = placement.new_plot("first", (40, 12), [])
    cx, cy = _center((plot.x, plot.y, plot.w, plot.h))
    assert abs(cx - WORLD_WIDTH / 2) < 4 and abs(cy - WORLD_HEIGHT / 2) < 4


def test_a_plot_avoids_the_ground_already_taken():
    taken = [(80, 20, 50, 20)]
    plot = placement.new_plot("second", (40, 12), taken)
    assert not placement.overlaps((plot.x, plot.y, plot.w, plot.h), taken[0], 0)


def test_the_same_name_gets_the_same_plot():
    assert placement.new_plot("same", (30, 9), []) == placement.new_plot("same", (30, 9), [])


def test_a_full_grove_grows_past_its_right_edge():
    plot = placement.new_plot("late", (30, 9), [(0, 0, WORLD_WIDTH, WORLD_HEIGHT)])
    assert plot.x >= WORLD_WIDTH
