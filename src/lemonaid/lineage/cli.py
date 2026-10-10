"""`lemonaid lemon parent` and `lemonaid lemon children`: links between lemons."""

import argparse
import dataclasses
import json
import sqlite3
import sys

import lemonaid.launch.cli
import lemonaid.messages.resume_cli

from .. import brief
from ..inbox import db
from . import describe, links


def _fail(args: argparse.Namespace, error: str) -> None:
    if args.json:
        print(json.dumps({"error": error}))
    else:
        print(error, file=sys.stderr)
    raise SystemExit(1)


def _named(conn: sqlite3.Connection, args: argparse.Namespace, name: str) -> str:
    """The Lemon-ID *name* means; `self` is the caller."""
    try:
        if name == "self":
            return brief.lemon.own_id(conn, args.channel or "")

        return brief.lemon.lemon_id(conn, name)
    except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
        _fail(args, str(error))
        raise


def _cmd_parent(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        child = _named(conn, args, "self" if args.use_self else args.lemon)
        try:
            if args.set:
                links.set_parent(conn, child, _named(conn, args, args.set))
            elif args.clear:
                links.clear_parent(conn, child)
        except links.LinkError as error:
            _fail(args, str(error))

        parent = links.parent_of(conn, child)
        described = describe.describe(conn, parent) if parent else None

    if args.json:
        print(
            json.dumps(
                {
                    "lemon_id": child,
                    "parent": dataclasses.asdict(described) if described else None,
                    "error": None,
                }
            )
        )
    else:
        print(parent or "none")


def _cmd_children(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        parent = _named(conn, args, "self" if args.use_self else args.lemon)
        children = [describe.describe(conn, child) for child in links.children_of(conn, parent)]

    if args.json:
        print(
            json.dumps(
                {
                    "lemon_id": parent,
                    "children": [dataclasses.asdict(c) for c in children],
                    "error": None,
                }
            )
        )
        return

    for child in children:
        print("\t".join((child.lemon_id, child.status or "-", child.channel or "-", child.brief)))


def _add_target(parser: argparse.ArgumentParser) -> None:
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--self", dest="use_self", action="store_true", help="The lemon running this command"
    )
    target.add_argument(
        "lemon", nargs="?", help="A Lemon-ID, channel, or brief name (attached or not)"
    )
    parser.add_argument("--channel", help="This lemon's channel, overriding self detection")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "lemon",
        help="Links between lemons, by stable Lemon-ID",
        description="A lemon's parent is the lemon that started it. Links are "
        "stored by Lemon-ID, so they survive resumes, renamed briefs, and tmux. "
        "A lemon with no parent belongs to whoever you treat as the default "
        "(for many, a control center). `start` launches one from config; `resume` brings one back.",
    )
    lemon_subparsers = parser.add_subparsers(dest="lemon_command", required=True)

    parent = lemon_subparsers.add_parser("parent", help="Show a lemon's parent, or set or clear it")
    _add_target(parent)
    change = parent.add_mutually_exclusive_group()
    change.add_argument(
        "--set",
        metavar="PARENT",
        help="Make PARENT (a Lemon-ID, channel, brief, or `self`) the parent",
    )
    change.add_argument("--clear", action="store_true", help="Remove the parent link")
    parent.set_defaults(func=_cmd_parent)

    children = lemon_subparsers.add_parser(
        "children", help="List a lemon's children with their brief status"
    )
    _add_target(children)
    children.set_defaults(func=_cmd_children)

    lemonaid.launch.cli.add_parser(lemon_subparsers)
    lemonaid.messages.resume_cli.add_parser(lemon_subparsers)
