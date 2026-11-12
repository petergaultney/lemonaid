"""Brief content shown inside the persistent tmux scratch pane."""

import json
import os
import subprocess

from .. import handlers, tmux
from ..config import Config, load_config
from ..tmux import follow, scratch
from . import target


def _tmux(*args: str) -> str | None:
    try:
        result = tmux.run(args, check=True, timeout=0.5)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    return result.stdout.strip()


def window_id(target_pane: str) -> str:
    return _tmux("display-message", "-p", "-t", target_pane, "#{window_id}") or ""


def _encode(found: target.Target, window: str) -> str:
    return json.dumps({"window": window, "target": target.to_json(found)})


def decode(value: str) -> tuple[target.Target, str] | None:
    try:
        data = json.loads(value)
        return target.from_json(json.loads(data["target"])), data["window"]
    except (KeyError, TypeError, ValueError):
        return None


def read(pane: str) -> tuple[target.Target, str] | None:
    return decode(_tmux("show-option", "-pqv", "-t", pane, follow.BRIEF_OPTION) or "")


Recorded = tuple[tuple[target.Target, str] | None, str]


def recorded(pane: str) -> Recorded:
    """The brief *pane* records and the window it is in, read before the TUI starts."""
    shown = read(pane)

    return (shown, window_id(pane)) if shown else (None, "")


def remember(pane: str, found: target.Target, window: str) -> None:
    """Record *found* as *pane*'s brief in *window*, without waking or focusing it."""
    _tmux("set-option", "-p", "-t", pane, follow.BRIEF_OPTION, _encode(found, window))


def clear(pane: str) -> None:
    _tmux("set-option", "-pu", "-t", pane, follow.BRIEF_OPTION)
    _tmux("send-keys", "-t", pane, follow.BRIEF_WAKE_KEY)


def _available(window: str) -> str | None:
    if not os.environ.get("TMUX") or not scratch.is_follow_enabled():
        return None

    pane = scratch.marked_pane()
    if (
        not pane
        or scratch.current_position(load_config().tmux_session.scratch_position) != "left"
        or window_id(pane) != window
    ):
        return None
    return pane


def beside(window: str) -> bool:
    """Whether the sidebar can show a brief for *window*: the scratch pane is on its left."""
    return _available(window) is not None


def show(found: target.Target, window: str) -> bool:
    """Replace the visible sidebar brief and focus the pane displaying it."""
    pane = _available(window)
    if pane is None:
        return False
    if _tmux("set-option", "-p", "-t", pane, follow.BRIEF_OPTION, _encode(found, window)) is None:
        return False
    _tmux("send-keys", "-t", pane, follow.BRIEF_WAKE_KEY)
    if _tmux("switch-client", "-t", pane) is None:
        clear(pane)
        return False
    return True


def switch_beside(
    metadata: dict[str, object], switch_source: str, config: Config, found: target.Target
) -> bool:
    """Put the main pane on a lemon and show *found* beside it, focus staying here.

    Called off the TUI's event loop: the switch is the slow part of browsing,
    and the brief is already drawn by the time it runs.
    """
    follow.publish({follow.KEEP_FOCUS_OPTION: "1"})
    try:
        if not handlers.handle_notification(metadata, config, switch_source=switch_source):
            return False
    finally:
        follow.publish({follow.KEEP_FOCUS_OPTION: None})  # a switch within one window fires no hook

    pane = os.environ.get("TMUX_PANE", "")
    return bool(pane) and show(found, window_id(pane))


def toggle(found: target.Target, window: str) -> bool:
    """Use the sidebar when it is beside *window*; otherwise let the caller use a popup."""
    pane = _available(window)
    if pane is None:
        return False

    current = read(pane)
    if current and current[1] == window:
        clear(pane)
    else:
        return show(found, window)

    return True
