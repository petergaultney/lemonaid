"""One line per limit window: usage, pace, projection, and reset."""

from . import color, pace, samples, settings


def _used(s: samples.Sample, now: float, config: settings.UsageConfig, use_color: bool) -> str:
    ratio = color.pace_ratio(s, now, config)
    text = f"{s.used_percent:g}% used" + (f" (pace {ratio:.2f}x)" if ratio is not None else "")
    if not use_color:
        return text

    return color.paint(
        text, None if ratio is None else color.pace_rgb(ratio, config.pace_color_ratios)
    )


def _projection(
    s: samples.Sample, now: float, config: settings.UsageConfig, use_color: bool
) -> str:
    p = pace.pace(s, now, config)
    if not p:
        return ""

    text = f"projected {p.projected_percent:.0f}% at reset"
    if p.projected_percent > 100:
        text += f", runs out {pace.clock(p.runout_at)}"

    return color.paint(text, color.projection_rgb(p.projected_percent)) if use_color else text


def lines(
    current: dict[str, samples.Sample],
    now: float,
    config: settings.UsageConfig,
    use_color: bool,
) -> list[str]:
    return [
        ", ".join(
            part
            for part in (
                f"{key}: {_used(s, now, config, use_color)}",
                f"elapsed {pace.elapsed_percent(s, now):.0f}%",
                _projection(s, now, config, use_color),
                f"resets {pace.resets(s, now)}",
            )
            if part
        )
        for key, s in current.items()
    ]
