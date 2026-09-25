"""`lemonaid inbox deliver`: run the Codex delivery service in the foreground."""

import argparse
import sys

from . import service


def cmd_deliver(args: argparse.Namespace) -> None:
    if not service.serve(args.interval, args.idle_exit, args.retry):
        print("A delivery service is already running", file=sys.stderr)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "deliver",
        help="Queue pending messages into Codex lemons' threads until none are left",
    )
    parser.add_argument(
        "--interval", type=float, default=1.0, help="Seconds between passes (default: 1)"
    )
    parser.add_argument(
        "--idle-exit",
        type=float,
        default=120.0,
        help="Exit after this many seconds with nothing pending; 0 runs forever (default: 120)",
    )
    parser.add_argument(
        "--retry",
        type=float,
        default=30.0,
        help="Seconds before retrying an inbox whose queue failed (default: 30)",
    )
    parser.set_defaults(func=cmd_deliver)
