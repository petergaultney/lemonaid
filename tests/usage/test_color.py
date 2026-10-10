import pytest

from lemonaid.usage import color, settings, summary

from .shared import MID, sample

RATIOS = settings.UsageConfig().pace_color_ratios


def test_configured_ratios_are_the_pace_color_stops():
    assert color.pace_rgb(RATIOS[0], RATIOS) == (0, 200, 100)
    assert color.pace_rgb(RATIOS[1], RATIOS) == (255, 220, 0)
    assert color.pace_rgb(RATIOS[2], RATIOS) == (255, 140, 0)
    assert color.pace_rgb(RATIOS[3], RATIOS) == (255, 50, 40)


def test_exactly_on_pace_is_a_yellow_green():
    r, g, b = color.pace_rgb(1.0, RATIOS)
    assert 0 < r < 255 and g > 200 and b < 100


def test_far_ahead_is_clamped_magenta_and_far_behind_blue():
    assert color.pace_rgb(10, RATIOS) == (255, 0, 200)
    assert color.pace_rgb(0, RATIOS) == (60, 120, 255)


@pytest.mark.parametrize("ratio", [0.2, 0.4, 0.6])
def test_well_behind_pace_is_cooler_than_green(ratio):
    r, _, b = color.pace_rgb(ratio, RATIOS)
    assert b > 100 and r <= 60


def test_cool_stops_mirror_the_warm_ones_around_green():
    green, _, orange, red = RATIOS

    assert color.pace_rgb(green * green / orange, RATIOS) == (0, 200, 220)
    assert color.pace_rgb(green * green / red, RATIOS) == (60, 120, 255)


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


def test_pace_runs_blue_to_magenta_with_green_below_one_and_magenta_well_past_red():
    blue, green, red, magenta = (
        color.pace_rgb(r, RATIOS) for r in (0.4, 0.85, RATIOS[3], RATIOS[3] * 1.2)
    )

    assert blue == (60, 120, 255)
    assert green == (0, 200, 100)
    assert red == (255, 50, 40)
    assert magenta == (255, 0, 200)
    assert color.pace_rgb(5, RATIOS) == magenta
    assert color.pace_rgb(1.5, RATIOS) not in (red, magenta)


def test_used_ramps_purple_blue_green_yellow_orange_red_exactly_at_100():
    assert [color.used_rgb(p) for p in (0, 20, 40, 60, 80, 100)] == [
        (130, 90, 220),
        (60, 120, 255),
        (0, 200, 100),
        (255, 220, 0),
        (255, 140, 0),
        (255, 50, 40),
    ]
    assert color.used_rgb(150) == (255, 50, 40)
    assert color.used_rgb(99) != (255, 50, 40)
