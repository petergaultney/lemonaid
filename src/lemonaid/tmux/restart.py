"""Replace the `lma` process in the scratch pane, keeping the pane itself.

The pane is not killed and remade. In follow mode it has been swapped into one
of your windows and every window it has visited holds a placeholder in its slot,
so killing it discards the arrangement that follow spent those visits building -
the pane comes back in the scratch session, and the next switch has to rebuild a
slot that was already there. `respawn-pane -k` replaces the process inside the
pane it is already in, so the pane id, its window, its size, and every
placeholder outlive the restart.

Until now the only way to pick up new code was `prefix+:kill-pane` then
`prefix+l`, which is that discard done by hand.
"""

import subprocess

from ..log import get_logger
from . import scratch

_log = get_logger("tmux.restart")


def _respawn(pane_id: str, command: str) -> bool:
    """Run `command` in `pane_id`, replacing whatever is running there."""
    result = subprocess.run(
        ["tmux", "respawn-pane", "-k", "-t", pane_id, command],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _log.warning("could not respawn %s: %s", pane_id, result.stderr.strip())
        return False

    return True


def restart_scratch() -> str:
    """Restart the scratch pane's TUI in place, or say why there is nothing to restart.

    Returns the line to print. A missing pane is not an error worth a non-zero
    exit: the thing you asked to be running is not running, and `prefix+l` is
    the command that starts it.
    """
    pane_id = scratch.marked_pane()
    if not pane_id:
        return "no scratch pane to restart; create one first"

    if not _respawn(pane_id, "lma --scratch"):
        return f"could not restart {pane_id}"

    # tmux 3.7 keeps pane options across a respawn, so this is usually a no-op.
    # Set anyway: the marker is the only handle the rest of lemonaid has on this
    # pane, and it is cheaper to re-assert than to depend on that staying true.
    scratch.remark_pane(pane_id)
    _log.info("restarted scratch pane %s", pane_id)
    return f"restarted {pane_id}"
