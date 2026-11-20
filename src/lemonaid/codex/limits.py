"""The Codex account's rate-limit windows, as Codex reports them."""

import typing as ty

from . import app_server

_TIMEOUT = 10.0


class Window(ty.NamedTuple):
    name: str  # "primary" or "secondary"
    used_percent: float
    resets_at: int  # Unix seconds
    minutes: int


def _windows(server: app_server.Server) -> list[Window]:
    [reply] = server.ask([("account/rateLimits/read", {})], _TIMEOUT)
    if "error" in reply:
        raise app_server.NoAnswer(str(reply["error"]))

    limits = reply["result"].get("rateLimits") or {}
    return [
        Window(name, float(w["usedPercent"]), int(w["resetsAt"]), int(w["windowDurationMins"]))
        for name in ("primary", "secondary")
        if (w := limits.get(name))
    ]


def windows() -> list[Window]:
    """Empty when Codex can't be asked or reports no limits."""
    return app_server.once(_windows, "rate limits", [], _TIMEOUT)
