from lemonaid.grove.layout import landmarks
from lemonaid.grove.model import WORLD_HEIGHT, WORLD_WIDTH


def test_the_packhouse_is_a_building_that_grows_with_its_sessions():
    small, large = landmarks.packhouse(1, []), landmarks.packhouse(6, [])
    assert small.texture == "house" and small.roundness == 12.0
    assert large.h > small.h


def test_the_stream_crosses_the_grove_west_to_east():
    stream = landmarks.default_stream()
    assert stream[0][0] == 0 and stream[-1][0] == WORLD_WIDTH
    assert all(0 < y < WORLD_HEIGHT for _, y in stream)
    assert [x for x, _ in stream] == sorted(x for x, _ in stream)


def test_the_roads_reach_the_grove_edges():
    across, down = landmarks.default_roads()
    assert across[0][0] == 0 and across[-1][0] == WORLD_WIDTH
    assert down[0][1] == 0 and down[-1][1] == WORLD_HEIGHT
