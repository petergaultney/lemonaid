from lemonaid.grove.draw import plots
from lemonaid.grove.model import WORLD_HEIGHT, WORLD_WIDTH


def test_to_edges_moves_world_border_ends_out_to_the_extent():
    line = [(0, 30), (100, 31), (WORLD_WIDTH, 30)]

    assert plots.to_edges(line, (300, 90)) == [(0, 30), (100, 31), (300, 30)]


def test_to_edges_extends_bottom_ends_and_leaves_inner_ends():
    line = [(100, 0), (101, 20), (102, WORLD_HEIGHT)]

    assert plots.to_edges(line, (300, 90)) == [(100, 0), (101, 20), (102, 90)]
