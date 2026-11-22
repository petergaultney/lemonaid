"""Starts the grove window in its hidden tmux session before the first summon, so the first press
of the summon key shows it at once instead of waiting seconds for it to start.
"""

import sys

from ..grove.window import control
from ..log import get_logger
from . import command

_log = get_logger("grove.window")


def warm() -> None:
    """Only on macOS, where a tmux key summons the window (`lemonaid grove window binding`), and
    only when it isn't running already."""
    if sys.platform != "darwin" or control.SESSION not in command.run(["list-keys"]).stdout:
        return

    if command.run(["has-session", "-t", f"={control.SESSION}"]).returncode == 0:
        return

    command.run(["new-session", "-d", "-s", control.SESSION, control.COMMAND])
    _log.info("started the grove window ahead of its summon key")
