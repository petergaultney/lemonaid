import math

import pytest

from lemonaid.grove.draw import plots
from lemonaid.grove.layout import landmarks, terrain
from lemonaid.grove.layout.arrange import arrange
from lemonaid.grove.model import WORLD_WIDTH, Plot

from .shared import NOW, STREAM, block, plot_data, stream_ground, stream_saved, tree


def test_new_blocks_stand_clear_of_the_roads_and_stream():
    blocks = tuple(block(f"g{i}", str(i), tree(f"t{i}")) for i in range(8))
    found, _ = arrange(blocks, stream_saved({}), NOW)
    assert not any(terrain.crosses(stream_ground(), plot) for plot in found.plots.values())


def test_an_end_on_the_worlds_border_runs_on_past_it():
    assert terrain.crosses(stream_ground(), Plot(WORLD_WIDTH + 40, 25, 30, 10, 4.5, 3, "rows"))


def test_a_block_saved_over_a_strip_of_the_stream_is_trimmed_off_it():
    saved = stream_saved(
        {"g": plot_data(20, 10, 40, 22)},
        {"g": {"a": {"x": 10, "y": 5, "letter": "a"}, "b": {"x": 10, "y": 19, "letter": "b"}}},
    )
    found, kept = arrange((block("g", "1", tree("a"), tree("b")),), saved, NOW)
    plot = found.plots["g"]
    assert (plot.x, plot.y, plot.w) == (20, 10, 40) and plot.h < 22
    assert not terrain.crosses(stream_ground(), plot)
    a, b = found.trees[("g", "a")], found.trees[("g", "b")]
    assert (a.cx, a.cy) == (10, 5)  # where it stood on the ground
    assert 0 <= b.cy <= plot.h  # cut off, so it stands afresh on the block
    assert kept["plots"]["g"]["h"] == plot.h


def test_a_block_saved_across_the_stream_moves_whole_to_free_ground():
    found, _ = arrange(
        (block("g", "1", tree("a")),), stream_saved({"g": plot_data(20, 24, 40, 16)}), NOW
    )
    plot = found.plots["g"]
    assert (plot.w, plot.h) == (40, 16) and not terrain.crosses(stream_ground(), plot)


def test_open_ground_over_the_stream_is_forgotten():
    saved = stream_saved(
        {"g": plot_data(20, 4, 40, 16), "gone": plot_data(80, 25, 30, 12, open_since=1.0)}
    )
    _, kept = arrange((block("g", "1", tree("a")),), saved, NOW)
    assert set(kept["plots"]) == {"g"}


def test_the_packhouse_stands_where_the_roads_meet():
    house = plot_data(90, 25, 24, 9, texture="house")
    found, _ = arrange((block("", "0", tree("hq")),), stream_saved({"": house}), NOW)
    assert (found.plots[""].x, found.plots[""].y) == (90, 25)


def _on(ground, x, y):
    return any(start <= x < end for start, end in ground.get(y, ()))


@pytest.mark.parametrize("extent", [WORLD_WIDTH, WORLD_WIDTH + 6, WORLD_WIDTH + 50, 1000, 2000])
def test_a_sloping_end_is_covered_however_far_the_grove_draws_it(extent):
    stream = tuple((x, y) for x, y in landmarks.default_stream())
    ground = terrain.covered((), stream)
    (x0, y0), (_, y1) = stream[-2], stream[-1]
    for k in range(401):
        x, y = x0 + (extent - x0) * k / 400, y0 + (y1 - y0) * k / 400
        assert _on(ground, math.floor(x), math.floor(y)), (x, y)


def _crowd():
    return block("g", "1", *(tree(f"t{i}") for i in range(50)))


def test_a_block_too_tall_for_the_world_still_stands_clear_of_terrain():
    saved = {"plots": {}, "trees": {}}
    found, kept = arrange((_crowd(),), saved, NOW)
    ground = terrain.of_saved(kept)
    assert not terrain.crosses(ground, found.plots["g"])
    assert arrange((_crowd(),), kept, NOW + 60)[0].plots["g"] == found.plots["g"]


def test_a_tall_saved_block_across_terrain_moves_clear_and_stays():
    saved = {"plots": {"g": plot_data(0, 1, 100, 60)}, "trees": {}}
    found, kept = arrange((block("g", "1", tree("a")),), saved, NOW)
    plot = found.plots["g"]
    assert (plot.w, plot.h) == (100, 60)
    assert not terrain.crosses(terrain.of_saved(kept), plot)
    assert arrange((block("g", "1", tree("a")),), kept, NOW + 60)[0].plots["g"] == plot


def test_a_block_a_gap_from_the_stream_stays_where_it_was_put():
    found, kept = arrange(
        (block("g", "1", tree("a")),), stream_saved({"g": plot_data(20, 35, 40, 16)}), NOW
    )
    assert (found.plots["g"].y, found.plots["g"].h) == (35, 16)
    assert kept["plots"]["g"]["clear"] == list(terrain.GAP)


def test_a_block_closer_to_the_stream_than_the_gap_is_moved_clear_of_it():
    found, kept = arrange(
        (block("g", "1", tree("a")),), stream_saved({"g": plot_data(20, 33, 40, 16)}), NOW
    )
    rect = found.plots["g"]
    assert not terrain.crosses_box(stream_ground(), (rect.x, rect.y, rect.w, rect.h), terrain.GAP)


def test_a_block_checked_once_is_not_checked_again():
    saved = stream_saved({"g": plot_data(20, 24, 40, 16, clear=list(terrain.GAP))})
    found, _ = arrange((block("g", "1", tree("a")),), saved, NOW)
    assert (found.plots["g"].x, found.plots["g"].y) == (20, 24)


def test_a_block_checked_without_a_gap_is_checked_again():
    saved = stream_saved({"g": plot_data(20, 33, 40, 16, clear=True)})
    found, _ = arrange((block("g", "1", tree("a")),), saved, NOW)
    assert found.plots["g"].y != 33


def test_a_drag_is_judged_by_the_cells_drawn_at_its_zoom():
    view = plots.View(0, 0, 1.5, 1.5)
    stream = [(x, y) for x, y in STREAM]
    assert plots.over_terrain(Plot(20, 24, 40, 8, 4.5, 3, "rows"), view, (), stream)
    assert not plots.over_terrain(Plot(20, 32, 40, 8, 4.5, 3, "rows"), view, (), stream)


def test_a_block_one_row_clear_of_the_stream_stays_where_it_was_put():
    found, _ = arrange(
        (block("g", "1", tree("a")),), stream_saved({"g": plot_data(20, 34, 40, 16)}), NOW
    )
    assert (found.plots["g"].y, found.plots["g"].h) == (34, 16)
