"""Switching the main pane to a lemon while the inbox pane keeps keyboard focus."""

import os
import subprocess
from collections import abc
from typing import Any

from . import follow, navigation, recorded_pane


def show(metadata: dict[str, Any], switch: abc.Callable[[], bool]) -> bool:
    """Run *switch* for a lemon whose pane exists, focus staying in the inbox pane.

    False means nothing was switched; a missing pane is for the caller's resuming path.
    """
    try:
        session, pane_id = recorded_pane.locate(metadata)
    except navigation.TmuxUnavailable:
        return False

    if session is None or pane_id is None or session == navigation.AMBIGUOUS:
        return False

    follow.publish({follow.KEEP_FOCUS_OPTION: "1"})
    try:
        if not switch():
            return False
    finally:
        follow.publish({follow.KEEP_FOCUS_OPTION: None})  # a switch within one window fires no hook

    # A lemon already in this window is switched to without the hook running.
    if inbox_pane := os.environ.get("TMUX_PANE"):
        subprocess.run(["tmux", "select-pane", "-t", inbox_pane], capture_output=True)

    return True
