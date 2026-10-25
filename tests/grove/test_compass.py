import pytest

from lemonaid.grove.draw import scene_parts
from lemonaid.grove.layout import arrange
from lemonaid.grove.tui import compass
from lemonaid.grove.tui.frame import Grove, clamp_pan
from lemonaid.grove.tui.keys import Where

from .shared import NOW, block, tree

BLOCKS = (block("oria", "1", tree("a")), block("", "0", tree("hq")))
GROVE = Grove(BLOCKS, *arrange.arrange(BLOCKS, {"plots": {}, "trees": {}}, NOW))
WIDTH, HEIGHT = 100, 24  # short enough that centering on the packhouse leaves room north
ACROSS = WIDTH / scene_parts.LEAST_SCALE[0]
DOWN = (HEIGHT - 2) / scene_parts.LEAST_SCALE[1]


def _press(key: str, where: Where | None = None) -> Where:
    moved = compass.step(GROVE, where or Where(), key, (WIDTH, HEIGHT), (2, 1))
    return clamp_pan(GROVE, moved, WIDTH, HEIGHT)


def test_home_and_shift_zero_center_the_view_on_the_packhouse():
    house = GROVE.arrangement.plots[""]
    middle = _press("home")
    assert middle == _press(")")
    x, y = middle.pan
    assert x < house.x + house.w / 2 < x + ACROSS
    assert y < house.y + house.h / 2 < y + DOWN


def test_the_compass_runs_clockwise_from_north():
    middle = _press("home").pan
    north, east, south, west = (_press(k).pan for k in ("!", "#", "%", "&"))
    assert north[1] < middle[1] and north[0] == middle[0]
    assert east[0] > middle[0] and east[1] == middle[1]
    assert south[1] > middle[1] or south[1] == middle[1]  # the grove may end below the middle
    assert west[0] < middle[0] and west[1] == middle[1]


def test_alt_and_a_digit_work_like_shift_and_it():
    assert _press("alt+3") == _press("#")


def test_shift_and_an_arrow_steps_a_whole_screen():
    start = Where(pan=(10.0, 0.0))
    assert _press("shift+right", start).pan[0] - 10 == pytest.approx(ACROSS)
    assert _press("shift+left", start).pan == (0.0, 0.0)


def test_an_arrow_nudges_the_view_a_few_cells():
    start = Where(pan=(10.0, 4.0))
    assert _press("right", start).pan[0] - 10 == pytest.approx(2 / scene_parts.LEAST_SCALE[0])
    assert _press("down", start).pan[1] - 4 == pytest.approx(1 / scene_parts.LEAST_SCALE[1])
    assert _press("left", Where()).pan == (0.0, 0.0)


def test_the_compass_stays_out_of_blocks_and_searches():
    assert compass.handles(Where(), "!")
    assert not compass.handles(Where(block="1", digits="1"), "!")
    assert not compass.handles(Where(search="x"), "home")
    assert not compass.handles(Where(), "a")
    assert not compass.handles(Where(block="1", digits="1"), "right")
