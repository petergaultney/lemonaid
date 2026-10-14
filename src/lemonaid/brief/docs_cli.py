"""`brief doc add|rm`: keep the list of documents a lemon produced."""

import argparse
from pathlib import Path

from ..config import load_config
from . import command, doc_table, verbs_cli


def _cmd(args: argparse.Namespace) -> None:
    path, error = command.own_brief(args)
    if path:
        vaults = load_config().brief.vaults
        error = verbs_cli.edit(
            path,
            lambda text: (
                doc_table.add(text, args.path, args.purpose, args.watch, vaults)
                if args.verb == "add"
                else doc_table.remove(text, args.path, vaults)
            ),
        )
    command.finish(args, {"path": str(path) if path else None}, error, str(path))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("doc", help="Add or remove a document in ### Docs")
    verbs = parser.add_subparsers(dest="verb", required=True)
    add = command.parser(verbs, "add", "Add or update a document")
    add.add_argument("path", type=Path)
    add.add_argument("purpose")
    add.add_argument(
        "--watch",
        type=doc_table.Watch,
        choices=list(doc_table.Watch),
        default=doc_table.Watch.RELAY_COMMENTS,
        help="Document events to watch (default: Relay comments)",
    )
    remove = command.parser(verbs, "rm", "Remove a document subscription")
    remove.add_argument("path", type=Path)
    parser.set_defaults(func=_cmd)
