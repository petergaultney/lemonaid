"""The `[usage]` config table: thresholds for `lemonaid usage --watch`."""

import math
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field

_RECOVERED_FRACTION = 0.9


@dataclass(frozen=True)
class UsageConfig:
    step_percent: float = 20
    pace_over_percent: float = 100
    pace_recovered_percent: float = 90
    pace_min_elapsed_percent: float = 5
    poll_seconds: float = 30
    overall_pace: bool = True
    overall_min_window_minutes: float = 1440
    weights: Mapping[str, float] = field(default_factory=dict)
    pace_color_ratios: tuple[float, float, float, float] = (
        0.85,
        1.05,
        1.25,
        1.4,
    )  # green, yellow, orange, red


def _number(data: dict, key: str, default: float, low: float, high: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        print(f"Warning: [usage] {key} must be a number from {low:g} to {high:g}", file=sys.stderr)

        return default

    return value


def _color_ratios(
    data: dict, default: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    if "pace_color_ratios" not in data:
        return default

    value = data["pace_color_ratios"]
    if (
        isinstance(value, list)
        and len(value) == 4
        and all(
            isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)
            for v in value
        )
        and 0 < value[0] < value[1] < value[2] < value[3]
    ):
        return (value[0], value[1], value[2], value[3])

    print(
        "Warning: [usage] pace_color_ratios must be four increasing positive numbers",
        file=sys.stderr,
    )

    return default


def _weights(data: dict) -> dict[str, float]:
    value = data.get("weights", {})
    if isinstance(value, dict) and all(
        isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and v > 0
        for v in value.values()
    ):
        return {str(k): float(v) for k, v in value.items()}

    print("Warning: [usage.weights] values must be positive numbers", file=sys.stderr)

    return {}


def _flag(data: dict, key: str, default: bool) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value

    print(f"Warning: [usage] {key} must be true or false", file=sys.stderr)

    return default


def parse(data: dict) -> UsageConfig:
    defaults = UsageConfig()
    over = _number(data, "pace_over_percent", defaults.pace_over_percent, 1, 1000)
    recovered = _number(data, "pace_recovered_percent", over * _RECOVERED_FRACTION, 1, 1000)
    if recovered > over:
        print(
            "Warning: [usage] pace_recovered_percent must not exceed pace_over_percent",
            file=sys.stderr,
        )
        recovered = over * _RECOVERED_FRACTION

    return UsageConfig(
        step_percent=_number(data, "step_percent", defaults.step_percent, 1, 100),
        pace_over_percent=over,
        pace_recovered_percent=recovered,
        pace_min_elapsed_percent=_number(
            data, "pace_min_elapsed_percent", defaults.pace_min_elapsed_percent, 0, 99
        ),
        poll_seconds=_number(data, "poll_seconds", defaults.poll_seconds, 1, 86400),
        pace_color_ratios=_color_ratios(data, defaults.pace_color_ratios),
        overall_min_window_minutes=_number(
            data,
            "overall_min_window_minutes",
            defaults.overall_min_window_minutes,
            0,
            10**6,
        ),
        overall_pace=_flag(data, "overall_pace", defaults.overall_pace),
        weights=_weights(data),
    )
