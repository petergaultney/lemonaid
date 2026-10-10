from lemonaid.usage import overall, samples, settings

from .shared import MID, WINDOW_S, sample

_CONFIG = settings.UsageConfig(overall_min_window_minutes=0)


def _current(**used: float) -> dict[str, samples.Sample]:
    return {key.replace("_", " "): sample(u) for key, u in used.items()}


def test_equal_weights_average_each_harness_worst_window():
    current = _current(claude_a=60, claude_b=30, codex_a=40)  # paces 1.2, 0.6, 0.8
    result = overall.overall(current, MID, _CONFIG)

    assert result
    assert abs(result.pace - 1.0) < 1e-9
    assert [w.window for w in result.windows] == ["claude a", "codex a", "claude b"]


def test_weights_shift_the_mean():
    config = settings.parse({"weights": {"claude": 3, "codex": 1}, "overall_min_window_minutes": 0})
    result = overall.overall(_current(claude_a=60, codex_a=40), MID, config)

    assert result
    assert abs(result.pace - 1.1) < 1e-9


def test_harness_without_usable_pace_is_left_out():
    current = {**_current(claude_a=60), "codex a": sample(5, WINDOW_S * 1.49)}  # 1% elapsed
    result = overall.overall(current, MID, _CONFIG)

    assert result
    assert abs(result.pace - 1.2) < 1e-9


def test_no_data_is_none():
    assert overall.overall({}, MID, _CONFIG) is None
    assert overall.overall(_current(claude_a=10), WINDOW_S * 0.01, _CONFIG) is None


def test_short_windows_do_not_count():
    short = settings.UsageConfig(overall_min_window_minutes=2000)

    assert overall.overall(_current(claude_a=60), MID, short) is None


def test_window_past_its_reset_is_skipped():
    assert overall.overall({"claude a": sample(10)}, WINDOW_S * 2, _CONFIG) is None
