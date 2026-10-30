"""`lemonaid watch restart`: restart running `watch --self` waiters into the installed lemonaid."""

import argparse
import sys

from . import registry, restart, restart_fallback

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
"""


def _chosen(a: argparse.Namespace) -> list[registry.Waiter]:
    if a.all:
        return [w for w in registry.running() if w.kind == "wait"]

    if a.use_self:
        return registry.mine(registry.owner_channel(a.channel or ""), "wait")

    return [w for w in registry.running() if w.kind == "wait" and set(a.lemons) & set(w.targets)]


def run(a: argparse.Namespace) -> int:
    if sum((a.all, a.use_self, bool(a.lemons))) != 1:
        print("Name lemons by Lemon-ID, or pass --self or --all")
        return 2

    chosen = _chosen(a)
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
    replaced = [*unasked, *restart_fallback.stuck(sent, a.wait)]
    for line in restart_fallback.replace(replaced):
        print(line)
    if not chosen and not hosts:
        print("No running watch --self waiter matches")
    return 0


def _cmd(a: argparse.Namespace) -> None:
    sys.exit(run(a))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "restart",
        help="Restart running watch --self waiters into the installed lemonaid",
        description=_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("lemons", nargs="*", help="Lemon-IDs whose watchers to restart")
    parser.add_argument("--self", dest="use_self", action="store_true", help="Your own watcher")
    parser.add_argument("--all", action="store_true", help="Every lemon's watcher")
    parser.add_argument(
        "--wait",
        type=float,
        default=30.0,
        help="Seconds to let asked watchers restart before stopping them (default 30)",
    )
    parser.add_argument("--channel", help="Your channel, overriding self detection")
    parser.set_defaults(func=_cmd)
