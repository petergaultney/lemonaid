"""`lemonaid lemon doctor`: the facts about some lemons, listing the ones that contradict their brief.

A lead asks about its children, the lemon nobody leads asks about the orphans
as well, and a sender asks about the one lemon that won't read its message.
"""

import argparse
import dataclasses
import json
import sqlite3
import sys
import time
import typing as ty

from .. import brief
from ..config import load_config
from ..inbox import db
from ..lineage import links
from ..log import get_logger
from ..messages import recipient
from ..watch import briefs_orphans
from . import facts

_log = get_logger("lemon_facts.cli")


def _fail(args: argparse.Namespace, error: str) -> ty.NoReturn:
    if args.json:
        print(json.dumps({"lemons": [], "skipped": [], "error": error}))
    else:
        print(error, file=sys.stderr)
    raise SystemExit(2)


def _attached_id(conn: sqlite3.Connection, entry: brief.attached.Attachment) -> str:
    """*entry*'s Lemon-ID, or "" for a pending attachment or an unreadable brief."""
    if not entry.channel:
        return ""

    try:
        return brief.lemon.current(conn, brief.identity.from_path(entry.path))
    except (OSError, ValueError) as error:
        _log.warning("Skipping brief %s: %s", entry.path, error)
        return ""


def _named(conn: sqlite3.Connection, target: str) -> str:
    """*target*'s Lemon-ID, or *target* itself when it names none, for `skipped`."""
    try:
        return brief.lemon.lemon_id(conn, target)
    except (LookupError, ValueError):
        return target


def _scope(conn: sqlite3.Connection, args: argparse.Namespace) -> list[str]:
    """The Lemon-IDs the arguments name, each once, in the order named."""
    ids = [_named(conn, target) for target in args.lemons]
    if args.children or args.orphans:
        own = brief.lemon.own_id(conn, args.channel or "")
        if args.children:
            ids += links.children_of(conn, own)
        if args.orphans:
            ids += briefs_orphans.find(conn, {own}, briefs_orphans.live_sessions)
    if args.all:
        ids += [
            lemon_id
            for lemon_id in (_attached_id(conn, entry) for entry in brief.attached.everything(conn))
            if lemon_id
        ]
    return list(dict.fromkeys(ids))


def _unreachable(found: facts.Facts) -> bool:
    """Deaf or dead, with a brief that isn't done and a row that isn't archived."""
    return (
        found.status != "done"
        and not found.archived
        and found.state in (recipient.DEAF, recipient.DEAD)
    )


def _ago(at: float | None, now: float) -> str:
    if at is None:
        return "unknown"

    minutes = int((now - at) // 60)
    if minutes < 120:
        return f"{minutes}m ago"

    return f"{minutes // 60}h ago" if minutes < 48 * 60 else f"{minutes // (24 * 60)}d ago"


def _line(found: facts.Facts, now: float) -> str:
    exited = (
        f"exited {_ago(found.exited_at, now)} ({found.exit_reason or 'no reason'})"
        if found.exited_at is not None
        else "no exit recorded"
    )
    return "  ".join(
        [
            found.lemon_id,
            f"Status: {found.status or '-'}",
            f"{found.state}: {found.state_detail}",
            *([f"pane: {found.pane}"] if found.pane else []),
            exited,
            f"active {_ago(found.last_activity, now)}",
            f"waiters {len(found.waiters_running)} running, {len(found.waiters_listed)} listed",
            *([f"{found.messages_queued} queued"] if found.messages_queued else []),
            *([f"{found.recent_starts} recent starts"] if found.recent_starts else []),
        ]
    )


def cmd_doctor(args: argparse.Namespace) -> None:
    if not (args.lemons or args.children or args.orphans or args.all):
        _fail(args, "Name lemons, or pass --children --self, --orphans --self, or --all")

    if (args.children or args.orphans) and not args.use_self:
        _fail(args, "--children and --orphans are relative to the caller: add --self")

    window = load_config().messages.autoresume_window
    with db.connect() as conn:
        try:
            ids = _scope(conn, args)
        except (LookupError, ValueError, brief.store.ChangedUnderneath) as error:
            _fail(args, str(error))
        gathered, skipped = [], []
        for lemon_id in ids:
            try:
                found = brief.lemon.attachment(conn, lemon_id)
            except (LookupError, ValueError):
                skipped.append(lemon_id)  # no such lemon, cleaned up, or not started
                continue

            gathered.append(facts.gather(found, lemon_id, links.parent_of(conn, lemon_id), window))

    shown = [found for found in gathered if args.verbose or _unreachable(found)]
    if args.json:
        print(
            json.dumps(
                {
                    "lemons": [dataclasses.asdict(found) for found in gathered],
                    "skipped": skipped,
                    "error": None,
                }
            )
        )
    else:
        now = time.time()
        unreachable = sum(1 for found in gathered if _unreachable(found))
        print(f"{len(gathered)} lemons, {unreachable} deaf or dead and not done or archived")
        for found in shown:
            print(_line(found, now))
    if any(_unreachable(found) for found in gathered):
        raise SystemExit(1)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "doctor",
        help="The facts about lemons, listing those that are deaf or dead",
        description="Report what lemonaid can see about each lemon: whether its harness runs, "
        "whether its inbox waiter is armed, what its pane shows, when and why it last exited, "
        "and which of its brief's waiters are running. Text output lists only lemons that are "
        "deaf or dead and whose brief isn't done or archived; --verbose lists them all, and "
        "--json gives every fact for every lemon in scope. Exits 1 when any lemon in scope is "
        "deaf or dead and not done or archived, 2 on an error. What the facts mean, and where "
        "they mislead, is in docs/for-lemons.md.",
    )
    parser.add_argument("lemons", nargs="*", help="Lemon-IDs, channels, or brief names")
    parser.add_argument(
        "--self", dest="use_self", action="store_true", help="Scope from the caller"
    )
    parser.add_argument(
        "--children", action="store_true", help="The caller's children (with --self)"
    )
    parser.add_argument(
        "--orphans",
        action="store_true",
        help="Lemons with no parent, or whose parent's session is gone (with --self)",
    )
    parser.add_argument(
        "--all", action="store_true", help="Every attached lemon (a ps and a pane capture each)"
    )
    parser.add_argument("--verbose", action="store_true", help="List every lemon in scope")
    parser.add_argument("--json", action="store_true", help="Every fact, as JSON")
    parser.add_argument("--channel", help="This lemon's channel, overriding self detection")
    parser.set_defaults(func=cmd_doctor)
