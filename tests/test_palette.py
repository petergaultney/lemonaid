import colorsys

from lemonaid import palette


def _rgb(hex_: str) -> tuple[float, float, float]:
    return tuple(int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def test_slots_are_saturated_and_readable_on_black() -> None:
    for slot in palette.SLOTS:
        assert colorsys.rgb_to_hls(*_rgb(slot))[2] > 0.5, slot
        assert (palette._luminance(*_rgb(slot)) + 0.05) / 0.05 >= 6.5, slot


def test_slots_cover_the_hue_wheel() -> None:
    hues = {round(colorsys.rgb_to_hls(*_rgb(s))[0] * 36) % 36 for s in palette.SLOTS}

    assert len(hues) == 36


def test_colour_for_is_stable() -> None:
    assert palette.colour_for("lemonaid") == palette.colour_for("lemonaid")
    assert palette.colour_for("lemonaid") in palette.SLOTS
