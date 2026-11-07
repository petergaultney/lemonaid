from lemonaid.grove.layout import terrain
from lemonaid.grove.layout.arrange import arrange

from .shared import NOW, block, plot_data, stream_ground, stream_saved, tree

# The stream runs along row 30 and covers rows 29 to 32, so the two-row gap held a block above
# it to row 26 and one below it from row 35.


def _arranged(plots, trees=None):
    blocks = tuple(block(name, str(i), tree(f"t{i}")) for i, name in enumerate(plots))
    return arrange(blocks, stream_saved(plots, trees), NOW)


def test_a_block_the_two_row_gap_held_off_the_stream_grows_a_row_toward_it():
    found, kept = _arranged({"above": plot_data(20, 10, 40, 17, clear=2)})
    plot = found.plots["above"]
    assert (plot.y, plot.h) == (10, 18)
    assert not terrain.crosses_box(stream_ground(), (plot.x, plot.y, plot.w, plot.h), terrain.GAP)
    assert kept["plots"]["above"]["clear"] == list(terrain.GAP)
    assert arrange((block("above", "0", tree("t0")),), kept, NOW + 60)[0].plots["above"] == plot


def test_a_block_growing_up_toward_the_stream_keeps_its_trees_on_theirstream_ground():
    found, kept = _arranged(
        {"below": plot_data(20, 35, 40, 16, clear=2)},
        {"below": {"t0": {"x": 10, "y": 5, "letter": "a"}}},
    )
    assert (found.plots["below"].y, found.plots["below"].h) == (34, 17)
    assert kept["trees"]["below"]["t0"]["y"] == 6


def test_a_block_well_clear_of_the_stream_keeps_its_size():
    found, _ = _arranged({"far": plot_data(20, 2, 40, 12, clear=2)})
    assert (found.plots["far"].y, found.plots["far"].h) == (2, 12)


def test_a_block_put_by_hand_on_the_stream_stays_there():
    found, _ = _arranged({"on": plot_data(20, 25, 40, 10, clear=2)})
    assert (found.plots["on"].y, found.plots["on"].h) == (25, 10)


def test_a_block_does_not_grow_into_its_neighbor():
    found, _ = _arranged(
        {"above": plot_data(20, 10, 40, 17, clear=2), "next": plot_data(20, 1, 40, 8, clear=2)}
    )
    assert found.plots["above"].h == 18
    found, _ = _arranged(
        {"above": plot_data(20, 10, 40, 17, clear=2), "under": plot_data(20, 28, 40, 1, clear=2)}
    )
    assert found.plots["above"].h == 17


def test_a_block_put_against_its_neighbor_still_grows():
    found, _ = _arranged(
        {"left": plot_data(1, 10, 40, 17, clear=2), "right": plot_data(41, 10, 40, 16, clear=2)}
    )
    assert (found.plots["left"].h, found.plots["right"].h) == (18, 16)


def test_a_block_does_not_grow_into_a_neighbor_put_against_it():
    found, _ = _arranged(
        {"above": plot_data(20, 10, 40, 17, clear=2), "under": plot_data(20, 27, 40, 9, clear=2)}
    )
    assert found.plots["above"].h == 17
