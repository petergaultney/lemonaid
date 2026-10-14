"""Command-line interface for moving groups in the inbox order."""

import argparse
import dataclasses
import json
import sys

from .. import lineage
from ..inbox import db
from . import arrangement, store


def _fail(args: argparse.Namespace, error: str) -> None:
    if args.json:
        print(json.dumps({"error": error}))
    else:
        print(error, file=sys.stderr)
    raise SystemExit(1)


def _cmd_move(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            group = store.find(conn, args.name)
        except (LookupError, store.GroupError) as error:
            _fail(args, str(error))
            raise

        ordered = store.all_groups(conn)
        current = next(i for i, item in enumerate(ordered, 1) if item.group_id == group.group_id)
        target = args.to if args.to is not None else current + (-1 if args.direction == "up" else 1)
        try:
            group = arrangement.move(conn, group, target)
        except ValueError as error:
            _fail(args, str(error))
            raise

        if args.json:
            print(
                json.dumps(
                    {
                        "group": {
                            "name": group.name,
                            "position": group.position,
                            "members": [
                                dataclasses.asdict(lineage.describe.describe(conn, lemon_id))
                                for lemon_id in group.members
                            ],
                        },
                        "error": None,
                    }
                )
            )
        else:
            print(f"{group.name}: position {target}")


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("move", help="Change a group's inbox order")
    parser.add_argument("name")
    parser.add_argument("--channel", help="This lemon's channel, overriding self detection")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--up", dest="direction", action="store_const", const="up")
    destination.add_argument("--down", dest="direction", action="store_const", const="down")
    destination.add_argument("--to", type=int, metavar="N", help="One-based position")
    parser.set_defaults(func=_cmd_move)
