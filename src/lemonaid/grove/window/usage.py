"""The usage table the inbox shows on `U`, as rows the page can draw: each limit window's pace, use,
elapsed time and reset, worst pace first, with the inbox's colors.
"""

import time

from ...config import Config
from ...log import get_logger
from ...usage import color, samples, table

_log = get_logger("grove.window")


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def rows(config: Config, now: float | None = None) -> list[dict]:
    """Empty, with a log line, when the usage files can't be read."""
    try:
        current = samples.current_samples()
    except (OSError, ValueError, KeyError, TypeError):
        _log.warning("could not read usage", exc_info=True)
        return []

    usage = config.usage
    return [
        {
            "window": r.window,
            "pace": "-" if r.pace is None else f"{r.pace:.2f}x",
            "paceColor": ""
            if r.pace is None
            else _hex(color.pace_rgb(r.pace, usage.pace_color_ratios)),
            "used": f"{r.used_percent:g}%",
            "usedColor": _hex(color.used_rgb(r.used_percent)),
            "elapsed": f"{r.elapsed_percent:.0f}%",
            "resets": r.resets,
        }
        for r in table.rows(current, now or time.time(), usage)
    ]
