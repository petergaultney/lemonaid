"""`lemonaid run`: run a command anywhere, and wake a lemon with its exit status when it ends.

Before it starts the command, it records `lemonaid watch command --wait <its own pid>` in the
lemon's brief, so the lemon's watcher reports the exit whichever terminal, window or `nohup`
the command runs under. It stays the command's parent to collect the exit status, passes on
SIGTERM and SIGHUP, and exits with the command's status.

    lemonaid run --self -- ./deploy.sh --env prod
    lemonaid run --lemon <Lemon-ID> -- make test      # where --self can't tell who you are
"""

import argparse
import dataclasses
import pathlib
import shlex
import signal
import subprocess
import sys
import time
import types

from ..brief import lemon, store, verbs_cli, waiters
from ..inbox import db
from . import command_record

_FORWARDED = (signal.SIGTERM, signal.SIGHUP)


def _brief(target: str, channel: str) -> tuple[str, pathlib.Path | None, str]:
    """The Lemon-ID and brief to wake, or an error."""
    try:
        with db.connect() as conn:
            lemon_id = lemon.lemon_id(conn, target) if target else lemon.own_id(conn, channel)
            path = lemon.brief_of(conn, lemon_id)
    except (LookupError, ValueError) as error:
        return "", None, str(error)
    if path is None or not path.is_file():
        return lemon_id, None, f"{lemon_id} has no brief to record the watch in"

    if error := store.outside_error(path):
        return lemon_id, None, error

    return lemon_id, path, ""


def _run(argv: list[str]) -> tuple[int, str]:
    """The command's exit status (128 + N for signal N) and the signal's name, if one ended it."""
    child: subprocess.Popen | None = None
    early: list[int] = []  # signals that arrived before the child's handle existed

    def forward(signum: int, frame: types.FrameType | None) -> None:
        if signum == signal.SIGINT:  # the terminal sends it to the command too
            return

        if child is None:
            early.append(signum)
        else:
            child.send_signal(signum)

    # A handler, not SIG_IGN, for SIGINT: an ignored signal stays ignored in the command.
    previous = {s: signal.signal(s, forward) for s in (*_FORWARDED, signal.SIGINT)}
    try:
        try:
            child = subprocess.Popen(argv)
        except OSError as error:
            print(f"lemonaid run: cannot start {argv[0]}: {error}", file=sys.stderr)
            return 127, ""

        for signum in early:
            child.send_signal(signum)
        status = child.wait()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    if status < 0:
        return 128 - status, signal.Signals(-status).name

    return status, ""


def run(a: argparse.Namespace) -> int:
    argv = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not argv:
        print("lemonaid run: name a command after --", file=sys.stderr)
        return 2

    lemon_id, path, error = _brief(a.lemon, a.channel)
    if path is None:
        print(f"lemonaid run: not started: {error}", file=sys.stderr)
        return 2

    record = command_record.begin(shlex.join(argv), str(pathlib.Path.cwd()), lemon_id)
    watch = f"lemonaid watch command --wait {record.pid}"
    if error := verbs_cli.edit(path, lambda text: waiters.add(text, watch), preserve_existing=True):
        print(f"lemonaid run: not started: could not record the watch: {error}", file=sys.stderr)
        return 2

    print(
        f"lemonaid run: pid {record.pid}; {lemon_id} is woken when `{record.command}` exits",
        file=sys.stderr,
    )
    status, name = _run(argv)
    command_record.write(dataclasses.replace(record, exit=status, signal=name, ended=time.time()))
    return status


def _cmd(a: argparse.Namespace) -> None:
    sys.exit(run(a))


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "run",
        help="Run a command and wake a lemon with its exit status when it ends",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--self", action="store_true", help="wake the lemon running this")
    who.add_argument(
        "--lemon",
        default="",
        metavar="LEMON",
        help="wake this lemon (a Lemon-ID, channel or brief name), for a command started "
        "where --self can't tell who you are, such as a new tmux window",
    )
    ap.add_argument("--channel", default="", help=argparse.SUPPRESS)
    ap.add_argument("command", nargs=argparse.REMAINDER, help="-- then the command to run")
    ap.set_defaults(func=_cmd)
