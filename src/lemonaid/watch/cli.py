"""`lemonaid watch`: blocking waiters that wake a lemon when something it watches changes."""

import argparse

from . import briefs_cli, doc_cli, file_cli, openclaw_cli, pr_cli, stop_cli


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "watch", help="Wait for changes to documents, PRs, files, or children's briefs"
    )
    watch_subparsers = parser.add_subparsers(dest="watch_command", required=True)
    doc_cli.add_parser(watch_subparsers)
    openclaw_cli.add_parser(watch_subparsers)
    pr_cli.add_parser(watch_subparsers)
    file_cli.add_parser(watch_subparsers)
    briefs_cli.add_parser(watch_subparsers)
    stop_cli.add_parser(watch_subparsers)
