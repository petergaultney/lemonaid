"""`lemonaid watch restart`: restart a lemon's waiters, or every lemon's watcher, into the installed lemonaid."""

import argparse
import sys

from ..brief import lemon
from ..inbox import db
from . import lemon_restart, registry, restart, restart_fallback

_HELP = """\
Ask running `watch --self` waiters, push scouts included, to restart into the
installed lemonaid. Each one restarts once nothing it has detected is waiting to be
delivered, with the same arguments, so no lemon has to rearm. A new lemonaid
version does this by itself the first time any lemonaid command runs.

Push scouts run in the scout host, so restarting any of them restarts the host,
which brings every scout back on the installed lemonaid.

A watcher that has not restarted after --wait seconds, and any started by a lemonaid
from before this command existed (they don't know the signal), is stopped instead,
and a push scout is started again in its place. Another waiter stays stopped for
its lemon to rearm.

A lemon named by Lemon-ID, or --self, also gets a push scout if it has no watcher.
Then each waiter it started by hand (`watch pr`, `watch slack` and the rest) is
stopped once its running watcher reads the same source from the brief, and tells
its lemon not to rearm it. A waiter the watcher doesn't follow keeps running. --all
restarts only watchers, and leaves hand-started waiters running.
"""


def _restart_watchers(chosen: list[registry.Waiter], wait: float) -> bool:
    """Ask *chosen* to restart, replacing those that don't; whether there were any."""
    hosts = (
        restart.send(w for w in registry.running() if w.kind == "host")
        if any(w.hosted for w in chosen)
        else []
    )
    for host in hosts:
        print(f"Asked the scout host (pid {host.pid}) to restart, with every scout it runs")
    chosen = [w for w in chosen if not w.hosted]
    sent = restart.send(chosen)
    for waiter in sent:
        print(f"Asked {', '.join(waiter.targets)}'s watcher (pid {waiter.pid}) to restart")
    unasked = [w for w in chosen if w not in sent]
    if unasked:
        print(f"{len(unasked)} older watchers don't restart on request")
    replaced = [*unasked, *restart_fallback.stuck(sent, wait)]
    for line in restart_fallback.replace(replaced):
        print(line)
    return bool(chosen or hosts)


def _lemons(a: argparse.Namespace) -> list[lemon_restart.Lemon]:
    with db.connect() as conn:
        targets = [lemon.self_channel(conn, a.channel or "")] if a.use_self else a.lemons
        return [lemon_restart.named(conn, target) for target in targets]


def run(a: argparse.Namespace) -> int:
    if sum((a.all, a.use_self, bool(a.lemons))) != 1:
        print("Name lemons by Lemon-ID, or pass --self or --all")
        return 2

    if a.all:
        if not _restart_watchers([w for w in registry.running() if w.kind == "wait"], a.wait):
            print("No running watch --self waiter matches")
        return 0

    try:
        lemons = _lemons(a)
    except LookupError as error:
        print(error)
        return 2

    ids = {one.lemon_id for one in lemons}
    watchers = [w for w in registry.running() if w.kind == "wait" and ids & set(w.targets)]
    _restart_watchers(watchers, a.wait)
    for one in lemons:
        if not any(one.lemon_id in w.targets for w in watchers):
            print(lemon_restart.start_watcher(one))
    by = registry.owner_channel(a.channel or "")
    for one in lemons:
        for line in lemon_restart.stop_hand_started(one, by, a.wait):
            print(line)
    return 0


def _cmd(a: argparse.Namespace) -> None:
    sys.exit(run(a))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "restart",
        help="Restart a lemon's waiters, or every watch --self waiter, into the installed lemonaid",
        description=_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("lemons", nargs="*", help="Lemon-IDs whose waiters to restart")
    parser.add_argument("--self", dest="use_self", action="store_true", help="Your own waiters")
    parser.add_argument(
        "--all", action="store_true", help="Every lemon's watcher, not its hand-started waiters"
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=30.0,
        help="Seconds to let watchers restart or start before giving up on them (default 30)",
    )
    parser.add_argument("--channel", help="Your channel, overriding self detection")
    parser.set_defaults(func=_cmd)
