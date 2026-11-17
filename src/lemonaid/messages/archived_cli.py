"""`lemonaid lemon archived`: lemons whose brief is in the attic, and whether `tell --wake`
could bring each back."""

import argparse
import datetime
import json
import sqlite3
import textwrap
import time
import typing as ty
from collections import abc
from pathlib import Path

from .. import brief, lineage
from ..brief import archive, archived_channel
from ..config import Config, load_config
from ..inbox import db
from ..places import audit
from . import autoresume, bring_back

_DAY = 24 * 60 * 60


class Archived(ty.NamedTuple):
    lemon_id: str
    brief: str
    changed: float  # when its brief was last written
    status: str
    now: str  # the first line of its `## Now`
    channel: str  # the session it was attached to when archived, or ""
    parent: str
    why_not: str  # why `tell --wake` would refuse it, or "" if it wouldn't


def _archived_briefs(conn: sqlite3.Connection) -> abc.Iterator[tuple[str, Path]]:
    for row in conn.execute("SELECT lemon_id, path FROM lemon_identities"):
        path = Path(row["path"])
        if archive.is_archived(path) and path.is_file():
            yield row["lemon_id"], path


def archived(conn: sqlite3.Connection, since: float, config: Config) -> list[Archived]:
    """Archived lemons whose brief changed after *since*, most recent first."""
    events = list(audit.entries(0))
    found = []
    for lemon_id, path in _archived_briefs(conn):
        changed = path.stat().st_mtime
        if changed < since:
            continue

        text = path.read_text(errors="replace")
        channel = archived_channel.of(conn, lemon_id)
        found.append(
            Archived(
                lemon_id,
                str(path),
                changed,
                brief.status.split(text).status,
                autoresume.now_line(text),
                channel,
                lineage.links.parent_of(conn, lemon_id) or "",
                bring_back.unwakeable(conn, lemon_id, config, events).why,
            )
        )
    return sorted(found, key=lambda each: each.changed, reverse=True)


def _line(each: Archived) -> str:
    day = datetime.datetime.fromtimestamp(each.changed).strftime("%Y-%m-%d")
    wake = "can wake" if not each.why_not else f"can't wake: {each.why_not}"
    now = f"\n    {textwrap.shorten(each.now, 160)}" if each.now else ""
    return f"{day}  {each.lemon_id}  [{each.status or 'no status'}]  {wake}{now}"


def cmd_archived(args: argparse.Namespace) -> None:
    since = 0.0 if args.all else time.time() - args.days * _DAY
    with db.connect() as conn:
        found = archived(conn, since, load_config())
    if args.json:
        print(json.dumps([each._asdict() for each in found], indent=2))
        return

    for each in found:
        print(_line(each))
    if not found:
        print("No archived lemons" + ("" if args.all else f" in the last {args.days:g} days"))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "archived",
        help="List lemons whose brief is archived, and whether tell --wake can bring each back",
        description="Lemons whose brief is in the attic, most recently changed first, with "
        "their last Status and Now line. `lemonaid tell --wake <Lemon-ID> <message>` brings "
        "back one marked `can wake`, and it reads the message once it is up.",
    )
    parser.add_argument(
        "--days", type=float, default=14, help="Only briefs changed this recently (default 14)"
    )
    parser.add_argument("--all", action="store_true", help="Every archived lemon")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    parser.set_defaults(func=cmd_archived)
