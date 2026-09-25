"""Brief content shown inside the persistent tmux scratch pane."""

import json
import os
import subprocess

from ..config import load_config
from ..tmux import follow, scratch
from . import target


def _tmux(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["tmux", *args], capture_output=True, text=True, check=True, timeout=0.5
        )
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


def clear(pane: str) -> None:
    _tmux("set-option", "-pu", "-t", pane, follow.BRIEF_OPTION)
    _tmux("send-keys", "-t", pane, follow.BRIEF_WAKE_KEY)


def toggle(found: target.Target, window: str) -> bool:
    """Use the sidebar when it is beside *window*; otherwise let the caller use a popup."""
    if not os.environ.get("TMUX") or not scratch.is_follow_enabled():
        return False

    pane = scratch.marked_pane()
    if (
        not pane
        or scratch.current_position(load_config().tmux_session.scratch_position) != "left"
        or window_id(pane) != window
    ):
        return False

    current = read(pane)
    if current and current[1] == window:
        clear(pane)
    else:
        if (
            _tmux("set-option", "-p", "-t", pane, follow.BRIEF_OPTION, _encode(found, window))
            is None
        ):
            return False

        _tmux("send-keys", "-t", pane, follow.BRIEF_WAKE_KEY)

    return True
