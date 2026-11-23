"""`lemonaid watch slack`: follow a Slack thread or channel, reporting each new message with its
author, time, permalink and text. Reads Slack with the session `lemonaid slack signin` saved;
never writes.

A link to a message, or to a reply, follows that message's thread. A channel's link
(`/archives/<channel>`) follows the messages posted in the channel itself; replies in its
threads come only when also sent to the channel. `--match <regex>` reports only the messages
whose text it matches (Python `re.search`, mentions as `@Name`; `(?i)` for any case), and
passes the others silently.

Listed under a brief's `## Watching`, the lemon's unified watcher follows it, and the scout
host's one Slack socket wakes it within seconds of a message. The subscription ends once the
brief is done or nothing has been posted for 7 days: the lemon hears it once, and the line
leaves `## Watching`.

Run with an attached brief, it records itself under `## Watching`; if the lemon's watcher runs,
it exits there. Otherwise it follows in the foreground, printing each batch (`--once`: the
first, then exits), until the lemon's watcher starts and takes over. It stops, exiting 1, when
Slack cannot be read until the user signs in. The first fetch takes the conversation as it is
now; `--after <ts>` reports the messages after that one instead.

    lemonaid watch slack https://acme.slack.com/archives/C0123ABCD/p1794857970806329
    lemonaid watch slack <permalink> --after 1794857970.806329
    lemonaid watch slack https://acme.slack.com/archives/C0123ABCD --match '(?i)deploy|release'
"""

import argparse
import re
import sys
import time

from ..config import load_config
from ..slack import permalink
from . import (
    brief_record,
    cursors,
    delivery,
    push_scout,
    registry,
    slack_events,
    wait_state,
)

_EVERY = 2.0  # seconds between polls in the foreground; each is a few file reads


def _conversation(value: str) -> permalink.Conversation:
    try:
        return permalink.parse(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _pattern(value: str) -> str:
    try:
        re.compile(value)
    except re.error as error:
        raise argparse.ArgumentTypeError(f"not a regex: {value!r}: {error}") from None
    return value


def _ts(value: str) -> str:
    """A Slack message ts; "" (no --after) passes, since argparse runs the default through this."""
    if value and not permalink.is_ts(value):
        raise argparse.ArgumentTypeError(
            f"not a Slack message ts such as 1794857970.806329: {value!r}"
        )
    return value


def _handed_over(owner: str, noun: str) -> str:
    return (
        f"{'push scout' if push_scout.running(owner) else 'watcher'} running; "
        f"it follows this {noun} from your brief's ## Watching, nothing to rearm"
    )


def run(a: argparse.Namespace) -> int:
    if error := brief_record.record(a, "slack"):
        print(f"not started: could not record waiter: {error}")
        return 2

    owner = cursors.owner(a.me)
    if owner and wait_state.is_armed(owner):
        print(_handed_over(owner, a.link.noun))
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
        a.match,
        False,
        directory,
        owner,
        deliver,
        problems.append,
        load_config().slack,
    )
    try:
        with registry.watching(a, "slack", a.link.target):
            while not (a.once and delivered):
                poll()
                if problems:
                    print(f"stopped: {problems[0]}")
                    return 1

                time.sleep(_EVERY)
                if owner and wait_state.is_armed(owner):
                    print(_handed_over(owner, a.link.noun))
                    return 0
    except KeyboardInterrupt:
        pass
    return 0


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "slack",
        help="Follow a Slack thread or channel: report each new message",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "link",
        type=_conversation,
        metavar="LINK",
        help="a channel's link, or a link to a thread or any reply in it",
    )
    ap.add_argument(
        "--after", type=_ts, default="", metavar="TS", help="first report messages after this ts"
    )
    ap.add_argument(
        "--match",
        type=_pattern,
        default="",
        metavar="REGEX",
        help="report only messages whose text this regex matches",
    )
    ap.add_argument("--me", default="", help="your lemon name, so two lemons' cursors stay apart")
    ap.add_argument("--once", action="store_true", help="print the first messages and exit")
    ap.set_defaults(func=lambda a: sys.exit(run(a)), status=None)
