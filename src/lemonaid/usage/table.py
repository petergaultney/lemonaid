"""One row per limit window, worst pace first, for the inbox's usage view."""

from collections.abc import Mapping
from dataclasses import dataclass

from . import color, pace, samples, settings


@dataclass(frozen=True)
class Row:
    window: str
    used_percent: float
    pace: float | None  # None while too little of the window has elapsed
    elapsed_percent: float
    resets: str


def rows(
    current: Mapping[str, samples.Sample], now: float, config: settings.UsageConfig
) -> list[Row]:
    built = [
        Row(
            key,
            s.used_percent,
            color.pace_ratio(s, now, config),
            pace.elapsed_percent(s, now),
            pace.resets(s, now),
        )
        for key, s in current.items()
    ]

    return sorted(built, key=lambda r: (r.pace is None, -(r.pace or 0)))
