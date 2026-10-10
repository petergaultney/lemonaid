from lemonaid.usage import settings


def test_defaults_when_absent():
    assert settings.parse({}) == settings.UsageConfig()


def test_overrides():
    assert settings.parse({"step_percent": 10, "poll_seconds": 5}).step_percent == 10


def test_invalid_value_falls_back_with_warning(capsys):
    assert settings.parse({"step_percent": "lots"}).step_percent == 20
    assert "step_percent" in capsys.readouterr().err


def test_recovered_above_over_is_rejected(capsys):
    assert (
        settings.parse({"pace_over_percent": 100, "pace_recovered_percent": 120})
        == settings.UsageConfig()
    )
    assert "pace_recovered_percent" in capsys.readouterr().err


def test_over_threshold_alone_scales_the_recovery_threshold():
    config = settings.parse({"pace_over_percent": 80})
    assert (config.pace_over_percent, config.pace_recovered_percent) == (80, 72)


def test_color_ratios_override_and_validation(capsys):
    assert settings.parse({"pace_color_ratios": [0.7, 1.2, 1.5, 2]}).pace_color_ratios == (
        0.7,
        1.2,
        1.5,
        2,
    )
    assert settings.parse({"pace_color_ratios": [1.5, 1.2, 2, 3]}).pace_color_ratios == (
        0.85,
        1.05,
        1.25,
        1.4,
    )
    assert "pace_color_ratios" in capsys.readouterr().err


def test_infinite_color_ratio_is_rejected(capsys):
    config = settings.parse({"pace_color_ratios": [0.8, 1.4, 1.8, float("inf")]})
    assert config.pace_color_ratios == (0.85, 1.05, 1.25, 1.4)
    assert "pace_color_ratios" in capsys.readouterr().err


def test_weights_parse_and_reject_non_positive(capsys):
    assert settings.parse({"weights": {"claude": 2}}).weights == {"claude": 2.0}
    assert settings.parse({"weights": {"claude": 0}}).weights == {}
    assert "weights" in capsys.readouterr().err


def test_overall_options(capsys):
    assert settings.parse({"overall_pace": False}).overall_pace is False
    assert settings.parse({"overall_pace": "no"}).overall_pace is True
    assert "overall_pace" in capsys.readouterr().err
    assert settings.parse({"overall_min_window_minutes": 60}).overall_min_window_minutes == 60
