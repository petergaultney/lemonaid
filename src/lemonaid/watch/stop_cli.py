"""`lemonaid watch stop --self`: stop the caller's own waiters, never another lemon's."""

import argparse
import sys

from ..brief import attached
from ..inbox import db
from . import brief_record, registry

_HELP = """\
Stop your own running waiters of any kind - inbox watch, watch pr, doc, file and
briefs - and remove each from your brief's `## Waiters`. With no KIND, stops all
of them; with a KIND and TARGET (a PR number, a path, a Lemon-ID), only that one.

Only waiters started by this version of lemonaid or later, with a lemon identity
(a harness session or --channel), are known; stop any other by its task or pid. Never `pkill -f` a waiter command: the pattern matches
every lemon's waiter on the machine.
"""


def run(a: argparse.Namespace) -> int:
    channel = registry.owner_channel(a.channel or "")
    if not channel:
        print("Can't tell which lemon this is; pass --channel")
        return 2

    found = registry.mine(channel, a.kind or "", a.target or "")
    if not found:
        print(
            "No running waiter of yours matches. One started before this lemonaid was "
            "installed, or without a lemon identity, isn't known; stop it by its task or pid"
        )
        return 0

    stopped: list[registry.Waiter] = []
    failed = False
    for waiter in found:
        try:
            registry.stop(waiter)
        except TimeoutError as error:
            print(error)
            failed = True
            continue

        stopped.append(waiter)
        print(f"Stopped {waiter.kind} waiter {', '.join(waiter.targets)} (pid {waiter.pid})")

    with db.connect() as conn:
        path = attached.by_channel(conn, [channel]).get(channel)
    if stopped and path is not None and (error := brief_record.forget(path, stopped)):
        print(f"Could not update ## Waiters in {path.name}: {error}")
        failed = True
    return 1 if failed else 0


def _cmd(a: argparse.Namespace) -> None:
    sys.exit(run(a))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "stop",
        help="Stop your own waiters (one, or all of them), by the lock each holds",
        description=_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--self", dest="use_self", action="store_true", required=True)
    parser.add_argument("--channel", help="Your channel, overriding self detection")
    parser.add_argument("kind", nargs="?", choices=registry.KINDS, help="Stop only this kind")
    parser.add_argument(
        "target", nargs="?", help="Stop only the waiter watching this PR, path or lemon"
    )
    parser.set_defaults(func=_cmd)
