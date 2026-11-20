from lemonaid.grove.layout import landmarks
from lemonaid.grove.model import WORLD_HEIGHT, WORLD_WIDTH

from .conftest import DEFAULT_ROADS, DEFAULT_STREAM


def test_the_packhouse_is_a_building_that_grows_with_its_sessions():
    small, large = landmarks.packhouse(1, []), landmarks.packhouse(6, [])
    assert small.texture == "house" and small.roundness == 12.0
    assert large.h > small.h


def test_the_stream_crosses_the_grove_west_to_east():
    stream = DEFAULT_STREAM()
    assert stream[0][0] == 0 and stream[-1][0] >= WORLD_WIDTH
    assert all(0 < y < WORLD_HEIGHT for _, y in stream)
    assert [x for x, _ in stream] == sorted(x for x, _ in stream)


def test_each_road_comes_in_from_a_grove_edge():
    for road in DEFAULT_ROADS():
        ends = (road[0], road[-1])
        assert any(x <= 0 or x >= WORLD_WIDTH or y <= 0 or y >= WORLD_HEIGHT for x, y in ends), road


def test_a_road_crosses_the_stream():
    stream_y = {x: y for x, y in DEFAULT_STREAM()}
    south = DEFAULT_ROADS()[-1]
    assert south[0][1] < stream_y[100] < south[-1][1]
