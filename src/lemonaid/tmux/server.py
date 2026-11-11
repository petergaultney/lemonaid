"""Which tmux server answers on a socket, told apart from no server at all.

A server's start time names it: a new server on the same socket has a later one,
and every session the inbox recorded carries the start time of the server it was
made on (`tmux_session_order`).
"""

import subprocess
import typing as ty

from ..log import get_logger
from . import command

_log = get_logger("tmux.server")

_TIMEOUT_SECONDS = 2

GONE: ty.Final = "gone"

# What tmux says when nothing listens on the socket: the file is missing, or left
# behind by a server that died.
_NO_SERVER = ("no server running on", "No such file or directory", "Connection refused")


def gone(stderr: str) -> bool:
    """Whether tmux's *stderr* says no server runs on the socket it was given."""
    return any(marker in stderr for marker in _NO_SERVER)


def started(socket: str | None) -> int | ty.Literal["gone"] | None:
    """The start time of the server on *socket*, GONE if none runs there, None if tmux can't say."""
    try:
        result = command.run(
            ["display-message", "-p", "#{start_time}"], socket, timeout=_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not ask tmux which server runs on %s: %s", socket, e)
        return None

    if result.returncode == 0 and result.stdout.strip().isdigit():
        return int(result.stdout.strip())

    if gone(result.stderr):
        return GONE

    _log.warning("tmux did not say which server runs on %s: %s", socket, result.stderr.strip())
    return None
