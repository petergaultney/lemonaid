"""How a tmux key reaches the running grove window: a line of text on a Unix socket.

The key writes the line with `nc -U` rather than through `lemonaid`, whose start-up alone takes
longer than the window takes to appear.
"""

import socket
from collections import abc
from pathlib import Path

from ...log import get_logger
from ..layout import state

_log = get_logger("grove.window")

SESSION = "_lma_grove_window"  # where the window runs when the summon key or the inbox starts it
COMMAND = "lemonaid grove window run"


def socket_path() -> Path:
    return state.path().with_name("grove-window.sock")


def dispatch(line: str, show: abc.Callable[[str], None], hide: abc.Callable[[], None]) -> None:
    """Carry out one request: `show <tmux client tty>` (the tty may be empty) or `hide`."""
    verb, _, client = line.strip().partition(" ")
    if verb == "show":
        show(client.strip())
    elif verb == "hide":
        hide()
    else:
        _log.warning("unknown request %r", line)


def send(line: str, path: Path | None = None) -> None:
    """Raises OSError when no grove window is listening."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(2)
        conn.connect(str(path or socket_path()))
        conn.sendall(line.encode() + b"\n")


def binding(key: str) -> str:
    """tmux.conf lines that summon the window over the client the key was pressed in, starting it
    in a hidden tmux session first if it isn't running. On anything but macOS the key opens the
    terminal grove's popup instead, so one tmux.conf serves every machine."""
    sock = '"${LEMONAID_STATE_DIR:-$HOME/.local/state/lemonaid}/grove-window.sock"'
    show = 'echo "show #{client_tty}" | nc -U "$S" 2>/dev/null'
    start = f'tmux new-session -d -s {SESSION} "{COMMAND}" 2>/dev/null'
    failed = f'tmux display-message "The grove window did not start: see tmux session {SESSION}"'
    # A window just started is shown as soon as it listens, waiting up to 10 seconds.
    wait = (
        f"i=0; until {show}; do i=$((i+1)); [ $i -lt 50 ] || {{ {failed}; exit; }}; sleep 0.2; done"
    )
    return "\n".join(
        [
            "if-shell 'test \"$(uname -s)\" = Darwin' {",
            f"  bind-key {key} run-shell -b 'S={sock}; {show} || {{ {start}; {wait}; }}'",
            "} {",
            f"  bind-key {key} run-shell -b 'lemonaid tmux popup grove'",
            "}",
        ]
    )
