"""`lemonaid watch`: watchers that wake a lemon when something it watches changes."""

import argparse
from collections import abc

from . import (
    briefs_cli,
    command_cli,
    doc_cli,
    file_cli,
    host_services,
    mentions_cli,
    notes_cli,
    notifications_wait_cli,
    openclaw_cli,
    pr_cli,
    reconcile,
    repo_cli,
    restart_cli,
    reviews_cli,
    scout_host,
    stop_cli,
    wait_cli,
)


def setup_parser(
    subparsers: argparse._SubParsersAction,
    host_services: abc.Sequence[host_services.Factory] = (),
) -> None:
    parser = subparsers.add_parser(
        "watch",
        help="Watch your brief with --self, or watch a document, PR, file, command or children",
    )
    wait_cli.add_arguments(parser)
    watch_subparsers = parser.add_subparsers(dest="watch_command")
    doc_cli.add_parser(watch_subparsers)
    openclaw_cli.add_parser(watch_subparsers)
    pr_cli.add_parser(watch_subparsers)
    repo_cli.add_parser(watch_subparsers)
    reviews_cli.add_parser(watch_subparsers)
    mentions_cli.add_parser(watch_subparsers)
    notifications_wait_cli.add_parser(watch_subparsers)
    file_cli.add_parser(watch_subparsers)
    command_cli.add_parser(watch_subparsers)
    briefs_cli.add_parser(watch_subparsers)
    notes_cli.add_parser(watch_subparsers)
    reconcile.add_parser(watch_subparsers)
    stop_cli.add_parser(watch_subparsers)
    restart_cli.add_parser(watch_subparsers)
    scout_host.add_parser(watch_subparsers, host_services)
