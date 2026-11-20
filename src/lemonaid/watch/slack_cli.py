"""`lemonaid watch slack`: follow a Slack thread, reporting each new reply with its author, time,
permalink and text. Reads Slack with the session `lemonaid slack signin` saved; never writes.

Listed under a brief's `## Watching`, the lemon's unified watcher follows it, and the scout
host's one Slack socket wakes it within a second of a reply. The subscription ends once the
brief is done or the thread has had no reply for 7 days: the lemon hears it once, and the line
leaves `## Watching`.

Run with an attached brief, it records itself under `## Watching`; if the lemon's watcher runs,
it exits there. Otherwise it follows the thread in the foreground, printing each batch of
replies (`--once`: the first, then exits), until the lemon's watcher starts and takes over. It
stops, exiting 1, when Slack cannot be read until the user signs in. The first fetch takes the
thread as it is now; `--after <ts>` reports replies after that message instead.

    lemonaid watch slack https://acme.slack.com/archives/C0123ABCD/p1794857970806329
    lemonaid watch slack <permalink> --after 1794857970.806329
"""

import argparse
import sys
import time

from ..config import load_config
from ..slack import permalink
from . import (
    brief_record,
    cursors,
    delivery,
    push_scout,
    slack_events,
    wait_state,
)

_EVERY = 2.0  # seconds between polls in the foreground; each is a few file reads


def _thread(value: str) -> permalink.Thread:
    try:
        return permalink.parse(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _ts(value: str) -> str:
    """A Slack message ts; "" (no --after) passes, since argparse runs the default through this."""
    if value and not permalink.is_ts(value):
        raise argparse.ArgumentTypeError(
            f"not a Slack message ts such as 1794857970.806329: {value!r}"
        )
    return value


def _handed_over(owner: str) -> str:
    return (
        f"{'push scout' if push_scout.running(owner) else 'watcher'} running; "
        "it follows this thread from your brief's ## Watching, nothing to rearm"
    )


def run(a: argparse.Namespace) -> int:
    if error := brief_record.record(a, "slack"):
        print(f"not started: could not record waiter: {error}")
        return 2

    owner = cursors.owner(a.me)
    if owner and wait_state.is_armed(owner):
        print(_handed_over(owner))
        return 0

    delivered: list[str] = []
    problems: list[str] = []

    def deliver(message: str) -> None:
        delivery.to_stdout(message)
        delivered.append(message)

    directory = cursors.directory("slack-foreground", a.me)  # apart from its watcher's cursors
    directory.mkdir(parents=True, exist_ok=True)
    poll = slack_events.poller(
        a.link,
        a.after,
        False,
        directory,
        owner,
        deliver,
        problems.append,
        load_config().slack,
    )
    try:
        while not (a.once and delivered):
            poll()
            if problems:
                print(f"stopped: {problems[0]}")
                return 1

            time.sleep(_EVERY)
            if owner and wait_state.is_armed(owner):
                print(_handed_over(owner))
                return 0
    except KeyboardInterrupt:
        pass
    return 0


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "slack",
        help="Follow a Slack thread: report each new reply",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "link", type=_thread, metavar="PERMALINK", help="a link to the thread or to a reply in it"
    )
    ap.add_argument(
        "--after", type=_ts, default="", metavar="TS", help="first report replies after this ts"
    )
    ap.add_argument("--me", default="", help="your lemon name, so two lemons' cursors stay apart")
    ap.add_argument("--once", action="store_true", help="print the first replies and exit")
    ap.set_defaults(func=lambda a: sys.exit(run(a)), status=None)
