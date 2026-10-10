"""One pace figure across harnesses: the weighted mean of each harness's worst window."""

from collections.abc import Mapping
from dataclasses import dataclass

from . import color, pace, samples, settings


@dataclass(frozen=True)
class WindowPace:
    window: str  # the sample key, for example `claude seven_day`
    harness: str
    pace: float


@dataclass(frozen=True)
class Overall:
    pace: float
    windows: tuple[WindowPace, ...]  # worst first


def window_paces(
    current: Mapping[str, samples.Sample], now: float, config: settings.UsageConfig
) -> list[WindowPace]:
    """Windows with a usable pace, worst first. Short windows and ones past their reset are skipped."""
    found = (
        WindowPace(key, key.split()[0], ratio)
        for key, s in current.items()
        if s.window_minutes >= config.overall_min_window_minutes
        and pace.elapsed_percent(s, now) <= 100
        and (ratio := color.pace_ratio(s, now, config)) is not None
    )

    return sorted(found, key=lambda w: w.pace, reverse=True)


def overall(
    current: Mapping[str, samples.Sample], now: float, config: settings.UsageConfig
) -> Overall | None:
    """None when no harness has a usable pace. Harnesses without one are left out, not counted as 0."""
    windows = window_paces(current, now, config)
    worst = {w.harness: w.pace for w in reversed(windows)}  # the worst window is written last
    if not worst:
        return None

    weights = {h: config.weights.get(h, 1.0) for h in worst}

    return Overall(
        sum(worst[h] * weights[h] for h in worst) / sum(weights.values()), tuple(windows)
    )
