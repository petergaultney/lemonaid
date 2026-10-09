import pytest

from lemonaid.usage import color, settings, summary

from .shared import MID, sample

RATIOS = settings.UsageConfig().pace_color_ratios


def test_configured_ratios_are_the_pace_color_stops():
    assert color.pace_rgb(0.8, RATIOS) == (0, 200, 100)
    assert color.pace_rgb(1.15, RATIOS) == (255, 220, 0)
    assert color.pace_rgb(1.4, RATIOS) == (255, 140, 0)
    assert color.pace_rgb(1.8, RATIOS) == (255, 50, 40)


def test_exactly_on_pace_is_a_yellow_green():
    r, g, b = color.pace_rgb(1.0, RATIOS)
    assert 0 < r < 255 and g > 200 and b < 100


def test_far_ahead_is_clamped_red_and_far_behind_blue():
    assert color.pace_rgb(10, RATIOS) == (255, 50, 40)
    assert color.pace_rgb(0, RATIOS) == (60, 120, 255)


@pytest.mark.parametrize("ratio", [0.2, 0.4, 0.6])
def test_well_behind_pace_is_cooler_than_green(ratio):
    r, _, b = color.pace_rgb(ratio, RATIOS)
    assert b > 100 and r <= 60


def test_cool_stops_mirror_the_warm_ones_around_green():
    assert color.pace_rgb(0.8 * 0.8 / 1.4, RATIOS) == (0, 200, 220)
    assert color.pace_rgb(0.8 * 0.8 / 1.8, RATIOS) == (60, 120, 255)


def test_projection_reaches_red_only_at_the_cap():
    assert color.projection_rgb(100) == (255, 50, 40)
    assert color.projection_rgb(250) == (255, 50, 40)
    assert color.projection_rgb(99) != (255, 50, 40)
    assert color.projection_rgb(0) == (60, 120, 255)


def test_projection_warms_as_it_approaches_the_cap():
    assert color.projection_rgb(55) == (0, 200, 100)
    assert color.projection_rgb(75) == (255, 220, 0)
    assert color.projection_rgb(90) == (255, 140, 0)


def test_summary_plain_has_no_escapes():
    plain = summary.lines({"c": sample(61)}, MID, settings.UsageConfig(), use_color=False)[0]
    assert "\033" not in plain
    assert "(pace 1.22x)" in plain and "projected 122% at reset" in plain


def test_used_and_projection_are_colored_differently():
    line = summary.lines({"c": sample(61)}, MID, settings.UsageConfig(), use_color=True)[0]
    used, projected = line.split("\033[0m")[:2]
    assert used != projected and "61% used" in used and "projected 122%" in projected
    assert "\033[38;2;255;50;40m" in projected  # over the cap is red


def test_reset_is_a_human_duration_then_the_date_in_parens():
    line = summary.lines(
        {"c": sample(30, MID + 3 * 86400 + 4 * 3600 + 120)}, MID, settings.UsageConfig(), False
    )[0]
    assert "resets in 3d 4h (" in line and line.endswith(")")
