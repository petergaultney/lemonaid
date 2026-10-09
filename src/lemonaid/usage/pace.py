"""Pace of usage against the straight line to a window's reset."""

import datetime
from dataclasses import dataclass

from . import samples, settings


@dataclass(frozen=True)
class Pace:
    elapsed_percent: float
    projected_percent: float  # at reset, if the rate so far continues
    runout_at: float  # epoch seconds when usage would reach 100%


def elapsed_percent(s: samples.Sample, now: float) -> float:
    length = s.window_minutes * 60

    return (now - (s.resets_at - length)) / length * 100


def pace(s: samples.Sample, now: float, config: settings.UsageConfig) -> Pace | None:
    """None while too little of the window has elapsed (or nothing is used) to project from."""
    elapsed = elapsed_percent(s, now)
    if elapsed < config.pace_min_elapsed_percent or s.used_percent <= 0:
        return None

    length = s.window_minutes * 60

    return Pace(
        elapsed,
        s.used_percent / elapsed * 100,
        s.resets_at - length + 100 / s.used_percent * elapsed / 100 * length,
    )


def clock(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch).astimezone().strftime("%a %H:%M %Z")


def _duration(seconds: float) -> str:
    minutes = max(0, int(seconds // 60))
    days, rest = divmod(minutes, 24 * 60)
    hours, minutes = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h"

    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def resets(s: samples.Sample, now: float) -> str:
    """For example `in 3d 4h (Tue 23:30 EDT)`."""
    return f"in {_duration(s.resets_at - now)} ({clock(s.resets_at)})"


def describe(s: samples.Sample, now: float, config: settings.UsageConfig) -> str:
    """Elapsed share plus projection (or run-out time)."""
    p = pace(s, now, config)
    if not p:
        return f"elapsed {elapsed_percent(s, now):.0f}%"

    if p.projected_percent > 100:
        return f"elapsed {p.elapsed_percent:.0f}%, runs out {clock(p.runout_at)}"

    return f"elapsed {p.elapsed_percent:.0f}%, projected {p.projected_percent:.0f}% at reset"


def over_message(key: str, s: samples.Sample, p: Pace) -> str:
    hours = (s.resets_at - p.runout_at) / 3600

    return (
        f"{key}: on track to run out {clock(p.runout_at)}, {hours:.1f}h before reset "
        f"(used {s.used_percent:g}% at {p.elapsed_percent:.0f}% of window)"
    )


def recovered_message(key: str, s: samples.Sample, p: Pace) -> str:
    return (
        f"{key}: back on pace, projected {p.projected_percent:.0f}% at reset "
        f"(used {s.used_percent:g}% at {p.elapsed_percent:.0f}% of window)"
    )
