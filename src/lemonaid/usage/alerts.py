"""Which usage alerts a new set of samples produces, given what was already alerted."""

from . import pace, samples, settings

_RESET_JITTER_S = 300


def _step(used_percent: float, step_percent: float) -> float:
    return min(100, used_percent // step_percent * step_percent)


def crossings(
    alerted: dict[str, dict],
    current: dict[str, samples.Sample],
    now: float,
    config: settings.UsageConfig,
) -> tuple[dict[str, dict], list[str]]:
    """New state plus alert lines.

    A window seen for the first time, or after a reset, is baselined silently for step crossings.
    Within a window a step alerts once: a lower reading (another session's older capture) never
    re-arms it.
    Pace alerts fire once when the projection goes over `pace_over_percent` and once when it falls
    back under `pace_recovered_percent`.
    """
    state, lines = {}, []
    for key, s in current.items():
        step, prev = _step(s.used_percent, config.step_percent), alerted.get(key)
        reset = prev is None or abs(prev["resets_at"] - s.resets_at) > _RESET_JITTER_S
        over = False if reset else prev.get("over", False)
        if reset:
            new_step = step
        else:
            new_step = max(step, prev["step"])
            if step > prev["step"]:
                lines.append(
                    f"{key}: crossed {step:g}% (used {s.used_percent:g}%, resets {pace.resets(s, now)}; "
                    f"{pace.describe(s, now, config)})"
                )

        if p := pace.pace(s, now, config):
            if not over and p.projected_percent > config.pace_over_percent:
                over = True
                lines.append(pace.over_message(key, s, p))
            elif over and p.projected_percent < config.pace_recovered_percent:
                over = False
                lines.append(pace.recovered_message(key, s, p))

        state[key] = {"step": new_step, "resets_at": s.resets_at, "over": over}

    return {**alerted, **state}, lines
