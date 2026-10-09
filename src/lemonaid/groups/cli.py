"""`lemonaid group`: name a set of lemons so the inbox can keep them together."""

import argparse
import dataclasses
import json
import sqlite3
import sys

from .. import brief, lineage
from ..inbox import db
from . import store, sync


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


def _lemons(conn: sqlite3.Connection, args: argparse.Namespace) -> list[str]:
    """The Lemon-IDs the arguments name, with every descendant of each under --tree."""
    named = [_named(conn, args, name) for name in args.lemons]
    if not args.tree:
        return named

    return list(
        dict.fromkeys(
            lemon_id
            for root in named
            for lemon_id in (root, *lineage.links.descendants(conn, root))
        )
    )


def _group(conn: sqlite3.Connection, args: argparse.Namespace, name: str) -> store.Group:
    try:
        return store.find(conn, name)
    except (LookupError, store.GroupError) as error:
        _fail(args, str(error))
        raise


def _as_json(conn: sqlite3.Connection, group: store.Group) -> dict:
    return {
        "name": group.name,
        "position": group.position,
        "members": [
            dataclasses.asdict(lineage.describe.describe(conn, lemon_id))
            for lemon_id in group.members
        ],
    }


def _print_group(conn: sqlite3.Connection, group: store.Group) -> None:
    print(group.name)
    for lemon in (lineage.describe.describe(conn, m) for m in group.members):
        print("\t" + "\t".join((lemon.lemon_id, lemon.status or "-", lemon.channel or "-")))


def _report(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
    group: store.Group,
    unwritten: list[str],
    **changed: list[str],
) -> None:
    """Print *group*, and any brief whose `Groups:` line couldn't be rewritten."""
    if args.json:
        print(
            json.dumps(
                {"group": _as_json(conn, group), **changed, "unwritten": unwritten, "error": None}
            )
        )
        return

    _print_group(conn, group)
    for path in unwritten:
        print(f"Couldn't update the Groups: line in {path}", file=sys.stderr)


def _cmd_list(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        if args.use_self or args.lemon:
            groups = store.groups_of(
                conn, _named(conn, args, "self" if args.use_self else args.lemon)
            )
        else:
            groups = store.all_groups(conn)

        if args.json:
            print(json.dumps({"groups": [_as_json(conn, g) for g in groups], "error": None}))
            return

        for group in groups:
            _print_group(conn, group)


def _cmd_create(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        lemons = _lemons(conn, args)
        try:
            group = store.create(conn, args.name)
        except store.GroupError as error:
            _fail(args, str(error))
            raise

        added = store.add(conn, group, lemons)
        _report(conn, args, store.find(conn, group.name), sync.write_lines(conn, added))


def _cmd_add(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        group = _group(conn, args, args.name)
        added = store.add(conn, group, _lemons(conn, args))
        _report(
            conn, args, store.find(conn, group.name), sync.write_lines(conn, added), added=added
        )


def _cmd_remove(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        group = _group(conn, args, args.name)
        removed = store.remove(conn, group, _lemons(conn, args))
        _report(
            conn,
            args,
            store.find(conn, group.name),
            sync.write_lines(conn, removed),
            removed=removed,
        )


def _cmd_rename(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            group = store.rename(conn, _group(conn, args, args.name), args.new_name)
        except store.GroupError as error:
            _fail(args, str(error))
            raise

        _report(conn, args, group, sync.write_lines(conn, group.members))


def _cmd_delete(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        group = _group(conn, args, args.name)
        store.delete(conn, group)
        unwritten = sync.write_lines(conn, group.members)

    if args.json:
        print(json.dumps({"deleted": group.name, "unwritten": unwritten, "error": None}))
        return

    print(f"Deleted {group.name}")
    for path in unwritten:
        print(f"Couldn't update the Groups: line in {path}", file=sys.stderr)


def _cmd_sync(args: argparse.Namespace) -> None:
    """Set each lemon's groups from its brief's line; one with no line is skipped."""
    with db.connect() as conn:
        read = {lemon_id: sync.read_line(conn, lemon_id) for lemon_id in _lemons(conn, args)}

    if args.json:
        lemons = [
            {"lemon_id": k, "groups": list(v) if v is not None else None} for k, v in read.items()
        ]
        print(json.dumps({"lemons": lemons, "error": None}))
        return

    for lemon_id, names in read.items():
        shown = "no Groups: line; left as it was" if names is None else ", ".join(names) or "-"
        print("\t".join((lemon_id, shown)))


def _common(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--channel", help="This lemon's channel, overriding self detection")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    return parser


def _members(parser: argparse.ArgumentParser, nargs: str) -> None:
    parser.add_argument(
        "lemons",
        nargs=nargs,
        metavar="LEMON",
        help="A Lemon-ID, channel, brief name or path (attached or not), or `self`",
    )
    parser.add_argument(
        "--tree", action="store_true", help="Each LEMON's children, their children, and so on too"
    )


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "group",
        help="Named groups of lemons, kept together in the inbox",
        description="A group is a name and a set of lemons, recorded by Lemon-ID "
        "so membership survives resumes and renamed briefs, and each member "
        "brief's Groups: line carries it to another machine. A lemon can be in "
        "any number of groups. See docs/groups.md.",
    )
    group_subparsers = parser.add_subparsers(dest="group_command", required=True)

    listing = _common(group_subparsers.add_parser("list", help="Every group and its members"))
    target = listing.add_mutually_exclusive_group()
    target.add_argument(
        "--self", dest="use_self", action="store_true", help="Only the groups I belong to"
    )
    target.add_argument("--lemon", help="Only the groups this lemon belongs to")
    listing.set_defaults(func=_cmd_list)

    create = _common(group_subparsers.add_parser("create", help="Make a group, with members"))
    create.add_argument("name")
    _members(create, "*")
    create.set_defaults(func=_cmd_create)

    add = _common(group_subparsers.add_parser("add", help="Put lemons in an existing group"))
    add.add_argument("name")
    _members(add, "+")
    add.set_defaults(func=_cmd_add)

    remove = _common(group_subparsers.add_parser("remove", help="Take lemons out of a group"))
    remove.add_argument("name")
    _members(remove, "+")
    remove.set_defaults(func=_cmd_remove)

    rename = _common(group_subparsers.add_parser("rename", help="Give a group a new name"))
    rename.add_argument("name")
    rename.add_argument("new_name")
    rename.set_defaults(func=_cmd_rename)

    delete = _common(
        group_subparsers.add_parser("delete", help="Remove a group; its lemons are untouched")
    )
    delete.add_argument("name")
    delete.set_defaults(func=_cmd_delete)

    sync_parser = _common(
        group_subparsers.add_parser(
            "sync", help="Set lemons' groups from their briefs' Groups: lines"
        )
    )
    _members(sync_parser, "+")
    sync_parser.set_defaults(func=_cmd_sync)
