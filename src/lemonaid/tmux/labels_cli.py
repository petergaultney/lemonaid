"""`lemonaid tmux labels`: have the scout host keep this tmux server's tab labels."""

import argparse
import subprocess
import sys

from ..watch import scout_start
from . import label_servers

_HELP = """\
Register this tmux server with the scout host, starting the host if none runs. The host
keeps each window's tab label in the window options @lemonaid_label and
@lemonaid_label_current, which window-status-format can show without running a process.
Run it from your tmux config with `run-shell -b`, so the labels return after tmux restarts.
"""


def _socket() -> str:
    try:
        found = subprocess.run(
            ["tmux", "display-message", "-p", "#{socket_path}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""

    return found.stdout.strip() if found.returncode == 0 else ""


def _cmd(args: argparse.Namespace) -> None:
    socket = args.socket or _socket()
    if not socket:
        print("Not in tmux, and no --socket given", file=sys.stderr)
        sys.exit(2)

    label_servers.register(socket)
    scout_start.ensure_host()


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "labels",
        help="Have the scout host keep this tmux server's tab labels",
        description=_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--socket", default="", help="The tmux server's socket (default: this one)")
    parser.set_defaults(func=_cmd)
