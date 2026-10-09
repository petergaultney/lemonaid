"""`lemonaid usage`: Claude and Codex subscription usage, and alerts as it crosses thresholds.

Without `--watch`, prints one line per limit window and exits. With `--watch`, blocks until a
window crosses a step (every 20% by default) or its pace projects running out before the
reset, prints one line per alert, and exits, so a Claude background Bash task wakes its session
once. Thresholds are set in the `[usage]` config table. The summary colors usage by pace and the
projection at reset by closeness to the cap (red means reaching it) when stdout is a terminal
and `NO_COLOR` is unset. Claude data comes from the statusLine command,
`lemonaid-claude-statusline`, so it updates only while a Claude session is running.
"""

import argparse
import os
import sys
import time

from .. import config
from . import alerts, samples, settings, state, summary


def _watch(thresholds: settings.UsageConfig) -> int:
    while True:
        new_state, lines = alerts.crossings(
            state.load(), samples.current_samples(), time.time(), thresholds
        )
        state.save(new_state)
        if lines:
            print("\n".join(lines), flush=True)

            return 0

        time.sleep(thresholds.poll_seconds)


def _use_color(a: argparse.Namespace) -> bool:
    return not a.no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ


def run(a: argparse.Namespace) -> int:
    thresholds = config.load_config().usage
    if a.watch:
        return _watch(thresholds)

    current = samples.current_samples()
    if not current:
        print(
            "no usage data yet (needs a Claude session with lemonaid-claude-statusline, or Codex rollouts)"
        )

        return 1

    print("\n".join(summary.lines(current, time.time(), thresholds, _use_color(a))))

    return 0


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "usage",
        help="Claude and Codex subscription usage; --watch blocks until an alert",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--no-color", action="store_true", help="never color the summary")
    parser.add_argument(
        "--watch", action="store_true", help="block until the next alert, print it, and exit"
    )
    parser.set_defaults(func=run)
