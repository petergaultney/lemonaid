"""`lemonaid watch`: watchers that wake a lemon when something it watches changes."""

import argparse

from . import (
    briefs_cli,
    doc_cli,
    file_cli,
    notes_cli,
    openclaw_cli,
    pr_cli,
    repo_cli,
    stop_cli,
    wait_cli,
)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "watch", help="Watch your brief with --self, or watch a document, PR, file or children"
    )
    wait_cli.add_arguments(parser)
    watch_subparsers = parser.add_subparsers(dest="watch_command")
    doc_cli.add_parser(watch_subparsers)
    openclaw_cli.add_parser(watch_subparsers)
    pr_cli.add_parser(watch_subparsers)
    repo_cli.add_parser(watch_subparsers)
    file_cli.add_parser(watch_subparsers)
    briefs_cli.add_parser(watch_subparsers)
    notes_cli.add_parser(watch_subparsers)
    stop_cli.add_parser(watch_subparsers)
