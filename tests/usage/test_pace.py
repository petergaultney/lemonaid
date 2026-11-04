import pytest

from lemonaid.usage import color, overall, pace, settings

from .shared import WINDOW_S, sample

_CONFIG = settings.UsageConfig()
_THREE_PERCENT_IN = WINDOW_S * 0.03


@pytest.mark.parametrize(
    ("used", "now", "has_pace"),
    [
        (8, _THREE_PERCENT_IN, True),  # used past 5% counts however little has elapsed
        (5, _THREE_PERCENT_IN, False),
        (2, WINDOW_S * 0.05, True),  # 5% elapsed counts however little is used
        (8, 0, False),  # nothing elapsed, so no ratio
    ],
)
def test_a_window_has_a_pace_once_enough_is_used_or_elapsed(used, now, has_pace):
    s = sample(used)

    assert (pace.pace(s, now, _CONFIG) is not None) is has_pace
    assert (color.pace_ratio(s, now, _CONFIG) is not None) is has_pace


def test_an_early_heavy_window_sets_the_overall_pace():
    result = overall.overall(
        {"claude seven_day": sample(8)},
        _THREE_PERCENT_IN,
        settings.UsageConfig(overall_min_window_minutes=0),
    )

    assert result
    assert result.pace == pytest.approx(8 / 3)


def test_the_used_threshold_is_configurable():
    config = settings.parse({"pace_min_used_percent": 10})

    assert config.pace_min_used_percent == 10
    assert pace.pace(sample(8), _THREE_PERCENT_IN, config) is None
