"""`lemonaid lemon end`: end one lemon whose brief has the Status its caller expects."""

import argparse
import json
import sqlite3
import subprocess
import sys

from ...brief import lemon
from ...config import load_config
from ...inbox import db
from ...log import get_logger
from ..restart import state
from . import coordinator, plan

_log = get_logger("launch.end.cli")

_HELP = """\
End one lemon without tossing the place it shares: stop its harness, its watcher,
push scout and every waiter it started, close its own pane (and its window, when no
other pane is in it), archive its inbox card, and move its brief to the attic as the
record.

It ends only a lemon whose brief's Status is one you expect: `done` unless you pass
--expect, which you may repeat (`--expect none` for a brief with no Status). Any
other Status is printed and nothing is done. A turn in progress is cut short.

A pane stays open when other jobs still run in it, when it is the last pane of its
session, or when its session is protected; the output says which. A lemon alone in its
tmux session is usually its place's lemon: `lemonaid place toss` cleans that up instead.
"""


def _place_note(planned: dict, tense: str) -> list[str]:
    """A lemon alone in its tmux session is usually its place's lemon."""
    if not planned.get("sole_session"):
        return []

    return [
        f"It {tense} the only lemon in tmux session {planned['sole_session']!r}:"
        " `lemonaid place toss` ends that place, its session and directory included."
    ]


def _print(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return

    planned = result["plan"]
    if result["phase"] != "dry-run":
        print(f"{planned['lemon_id']}: {result['phase']}")
        for line in result.get("done", []):
            print(f"  {line}")
        for line in [*filter(None, [result.get("error")]), *_place_note(planned, "was")]:
            print(line)
        return

    source = planned["source"]
    print(f"{planned['lemon_id']}: would end")
    for line in [
        *([f"stop its harness, pid {source['pid']}"] if source else []),
        *(["archive its inbox card"] if planned["card"] else []),
        *(f"stop its {waiter}" for waiter in planned["waiters"]),
        "keep its brief, already in the attic"
        if planned["archived"]
        else f"move its brief {planned['brief']} to the attic",
        planned["closing"],
    ]:
        print(f"  {line}")
    for line in _place_note(planned, "is"):
        print(line)


def _caller(conn: sqlite3.Connection, channel: str) -> str:
    """The calling lemon, for the record; a person at a shell is the user."""
    try:
        return lemon.own_id(conn, channel)
    except LookupError as error:
        _log.info("Ending a lemon for the user: %s", error)
        return "user"


def _planned(args: argparse.Namespace) -> dict:
    with db.connect() as conn:
        return plan.build(
            conn,
            args.lemon,
            load_config(),
            args.expect or ["done"],
            _caller(conn, args.channel or ""),
        )


def _cmd(args: argparse.Namespace) -> None:
    try:
        if args.status:
            result = state.get(args.status)
        elif not args.lemon:
            raise ValueError("Name one lemon, or use --status OPERATION_ID")
        else:
            planned = _planned(args)
            result = (
                {"phase": "dry-run", "plan": planned}
                if args.dry_run
                else {"phase": "ended", "plan": planned, "done": coordinator.run(planned)}
            )
        _print(result, args.json)
    except (LookupError, ValueError, OSError, TimeoutError, subprocess.SubprocessError) as error:
        if args.json:
            print(json.dumps({"error": str(error)}))
        else:
            print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "end",
        help="End one lemon: its harness, waiters and pane; its brief goes to the attic",
        description=_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("lemon", nargs="?", help="A Lemon-ID, channel, or brief name")
    parser.add_argument(
        "--dry-run", action="store_true", help="Check and print what it would do, changing nothing"
    )
    parser.add_argument(
        "--status", metavar="OPERATION_ID", help="An interrupted end's saved record"
    )
    parser.add_argument(
        "--expect",
        action="append",
        metavar="STATUS",
        help="A Status its brief may have; repeat for several (default done; none for no Status)",
    )
    parser.add_argument("--channel", help="Your channel, overriding self detection")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=_cmd)
