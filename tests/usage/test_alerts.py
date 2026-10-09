from lemonaid.usage import alerts, settings

from .shared import MID, WINDOW_S, sample

DEFAULT = settings.UsageConfig()


def test_first_sight_is_silent_then_crossing_alerts_once():
    state, lines = alerts.crossings({}, {"codex": sample(30)}, MID, DEFAULT)
    assert lines == [] and state["codex"]["step"] == 20

    state, lines = alerts.crossings(state, {"codex": sample(41)}, MID, DEFAULT)
    assert len(lines) == 1 and "crossed 40%" in lines[0] and "elapsed 50%" in lines[0]

    _, lines = alerts.crossings(state, {"codex": sample(45)}, MID, DEFAULT)
    assert lines == []


def test_reset_rearms():
    state, _ = alerts.crossings({}, {"c": sample(90, 1000)}, 0, DEFAULT)
    state, lines = alerts.crossings(state, {"c": sample(3, 9000 + WINDOW_S)}, 9000, DEFAULT)
    assert lines == [] and state["c"]["step"] == 0

    _, lines = alerts.crossings(state, {"c": sample(21, 9000 + WINDOW_S)}, 9000, DEFAULT)
    assert len(lines) == 1 and "crossed 20%" in lines[0]


def test_skipped_steps_report_the_highest():
    state, _ = alerts.crossings({}, {"c": sample(5)}, MID, DEFAULT)
    _, lines = alerts.crossings(state, {"c": sample(65)}, MID, DEFAULT)
    crossed = [line for line in lines if "crossed" in line]
    assert len(crossed) == 1 and "crossed 60%" in crossed[0]


def test_over_pace_alerts_once_then_recovers_below_hysteresis_band():
    state, lines = alerts.crossings({}, {"c": sample(61)}, MID, DEFAULT)  # projects 122%
    assert len(lines) == 1 and "on track to run out" in lines[0]

    state, lines = alerts.crossings(state, {"c": sample(62)}, MID, DEFAULT)
    assert lines == []

    state, lines = alerts.crossings(state, {"c": sample(48)}, MID, DEFAULT)  # projects 96%
    assert lines == []

    _, lines = alerts.crossings(state, {"c": sample(44)}, MID, DEFAULT)  # projects 88%
    assert len(lines) == 1 and "back on pace" in lines[0]


def test_no_pace_alert_in_first_five_percent():
    _, lines = alerts.crossings({}, {"c": sample(10)}, WINDOW_S * 0.04, DEFAULT)
    assert lines == []


def test_thresholds_are_configurable():
    config = settings.UsageConfig(
        step_percent=10, pace_over_percent=150, pace_min_elapsed_percent=60
    )
    state, _ = alerts.crossings({}, {"c": sample(5)}, MID, config)
    state, lines = alerts.crossings(state, {"c": sample(11)}, MID, config)
    assert len(lines) == 1 and "crossed 10%" in lines[0]

    _, lines = alerts.crossings(
        state, {"c": sample(70)}, MID, config
    )  # 140% projected, and before min elapsed
    assert [line for line in lines if "run out" in line] == []
