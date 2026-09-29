"""`lemonaid watch`: blocking waiters that wake a lemon when something it watches changes."""

import argparse

from . import doc_cli, openclaw_cli, pr_cli


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "watch", help="Wait for changes to documents or PRs a lemon watches"
    )
    watch_subparsers = parser.add_subparsers(dest="watch_command", required=True)
    doc_cli.add_parser(watch_subparsers)
    openclaw_cli.add_parser(watch_subparsers)
    pr_cli.add_parser(watch_subparsers)
