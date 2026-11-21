"""`lemonaid grove graft|ungraft|grafts`: draw a lemon on another lemon's tree, wherever it runs."""

import argparse
import json
import sqlite3
import sys
import typing as ty

from .. import brief
from ..inbox import db
from . import grafts


def _fail(args: argparse.Namespace, error: str) -> ty.NoReturn:
    if args.json:
        print(json.dumps({"error": error}))
    else:
        print(error, file=sys.stderr)
    raise SystemExit(1)


def _named(conn: sqlite3.Connection, args: argparse.Namespace, name: str) -> str:
    """The Lemon-ID *name* means, or the channel of a session with no brief; `self` is the caller."""
    try:
        if name == "self":
            return brief.lemon.own_id(conn)

        return brief.lemon.lemon_id(conn, name)
    except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
        if db.get_by_channel(conn, name, unread_only=False):
            return name

        _fail(args, str(error))


def _live(conn: sqlite3.Connection) -> set[str]:
    """The channels and Lemon-IDs of the lemons the grove draws."""
    channels = {n.channel for n in db.get_active(conn)}
    ids = brief.identity.by_channel(conn)
    return channels | {ids[channel] for channel in channels if channel in ids}


def _cmd_graft(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        lemon, onto = _named(conn, args, args.lemon), _named(conn, args, args.onto)
        try:
            grafts.graft(conn, lemon, onto)
        except grafts.GraftError as error:
            _fail(args, str(error))
        waiting = onto not in _live(conn)
    if args.json:
        print(json.dumps({"lemon": lemon, "onto": onto, "waiting": waiting, "error": None}))
    else:
        print(f"{lemon} is on {onto}'s tree" + (f" once {onto} is live" if waiting else ""))


def _cmd_ungraft(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        lemon = _named(conn, args, args.lemon)
        channels = [c for c, i in brief.identity.by_channel(conn).items() if i == lemon]
        removed = grafts.ungraft(conn, [lemon, args.lemon, *channels])
    if args.json:
        print(json.dumps({"lemon": lemon, "ungrafted": bool(removed), "error": None}))
    else:
        print(f"{lemon} is back on its own tree" if removed else f"{lemon} has no graft")


def _cmd_list(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        rows, live = grafts.listed(conn), _live(conn)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "lemon": row["lemon"],
                        "onto": row["onto"],
                        "grafted_at": row["grafted_at"],
                        "waiting": row["onto"] not in live,
                    }
                    for row in rows
                ]
            )
        )
        return

    for row in rows:
        waiting = "" if row["onto"] in live else f", waiting for {row['onto']}"
        print(f"{row['lemon']} on {row['onto']}'s tree{waiting}")
    if not rows:
        print("No lemon is grafted onto another's tree")


def add_parsers(grove_subparsers: argparse._SubParsersAction) -> None:
    lemon_help = "A Lemon-ID or its name (as StoveHub), a brief, a channel, or self"
    graft = grove_subparsers.add_parser(
        "graft", help="Draw a lemon on another lemon's tree, wherever it runs"
    )
    graft.add_argument("lemon", help=lemon_help)
    graft.add_argument(
        "--onto", required=True, metavar="LEMON", help="The lemon whose tree it joins"
    )
    graft.add_argument("--json", action="store_true", help="Print the result as JSON")
    graft.set_defaults(func=_cmd_graft)

    ungraft = grove_subparsers.add_parser(
        "ungraft", help="Put a grafted lemon back on its own tree"
    )
    ungraft.add_argument("lemon", help=lemon_help)
    ungraft.add_argument("--json", action="store_true", help="Print the result as JSON")
    ungraft.set_defaults(func=_cmd_ungraft)

    listing = grove_subparsers.add_parser("grafts", help="List the lemons on another lemon's tree")
    listing.add_argument("--json", action="store_true", help="Print them as JSON")
    listing.set_defaults(func=_cmd_list)
