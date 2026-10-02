"""`lemonaid inbox arrange`: try an arranger against the live inbox without `lma`."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ...config import Config, load_config
from .. import db, emoji, order, pins, view
from ..tui import brief_cards
from . import answer, child, serve


def _snapshot(
    config: Config, layout: str, width: int
) -> tuple[dict[str, Any], list[db.Notification], list[db.Notification]]:
    """The snapshot `lma` would send now, with the inbox's own shown and folded rows."""
    now = time.time()
    with db.connect() as conn:
        active = view.ordered_active(
            conn, None, brief_cards.BriefCache(), config.tui.mid_turn_working, now
        )
        pinned = frozenset(pins.pinned_positions(conn))
        emojis = emoji.by_channel(conn)
    shown, folded = order.fold(
        active.rows, view.statuses(active.cards), pinned, config.tui.fold_statuses
    )
    return (
        view.snapshot(active, shown, folded, pinned, emojis, layout, width, now),
        shown,
        folded,
    )


def _print_rows(title: str, rows: list[db.Notification]) -> None:
    print(title)
    for n in rows:
        print(f"  {n.id:>6}  {'●' if n.is_unread else ' '} {n.name or n.channel}")


def cmd_snapshot(args: argparse.Namespace) -> None:
    snap, _, _ = _snapshot(load_config(), args.layout, args.width)
    print(json.dumps({**snap, "now": time.time()}, indent=2 if args.pretty else None))


def cmd_check(args: argparse.Namespace) -> None:
    config = load_config()
    command = args.command or config.inbox.arrange
    if not command:
        sys.exit("No [inbox] arrange is configured; pass --command to try one.")

    snap, shown, folded = _snapshot(config, args.layout, args.width)
    started = time.perf_counter()
    try:
        done = subprocess.run(
            child.parse_command(command),
            input=json.dumps({**snap, "now": time.time()}) + "\n",
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
    except OSError as e:
        sys.exit(f"can't start {command!r}: {e}")
    except subprocess.TimeoutExpired:
        sys.exit(f"no answer in {args.timeout:g}s")
    elapsed = time.perf_counter() - started

    if done.stderr:
        print("stderr:\n" + done.stderr.rstrip(), file=sys.stderr)
    first = next(iter(done.stdout.splitlines()), "")
    if not first:
        sys.exit(f"no answer: exited {done.returncode} without printing a line")

    try:
        arranged = answer.apply(
            json.loads(first), shown, folded, config.inbox.arrange_may_fold_unread
        )
    except (json.JSONDecodeError, answer.AnswerError) as e:
        sys.exit(f"unusable answer: {e}")

    _print_rows(f"{len(arranged.shown)} rows:", arranged.shown)
    if arranged.folded:
        _print_rows(f"folded, as {arranged.fold_label or 'folded'!r}:", arranged.folded)
    print(f"\nanswered in {elapsed * 1000:.0f} ms, start-up included")
    for problem in arranged.problems:
        print(f"problem: {problem}")
    sys.exit(1 if arranged.problems else 0)


def cmd_serve(args: argparse.Namespace) -> None:
    serve.serve(serve.load(args.file))


def _add_view_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--layout", choices=("sidebar", "table"), default="sidebar")
    parser.add_argument("--width", type=int, default=40, help="Pane width to report")


def add_parser(inbox_subparsers: argparse._SubParsersAction) -> None:
    parser = inbox_subparsers.add_parser(
        "arrange",
        help="Try the [inbox] arrange program that orders lma's list",
        description="An arranger is a program lma keeps running. It reads one JSON snapshot "
        "of the inbox per line and answers each with one JSON line saying the order and what "
        "folds. See docs/arrange.md.",
    )
    sub = parser.add_subparsers(dest="arrange_command", required=True)

    check = sub.add_parser(
        "check", help="Send the arranger one snapshot of the live inbox and report on its answer"
    )
    check.add_argument(
        "--command", default="", help="Arranger to try instead of the configured one"
    )
    check.add_argument("--timeout", type=float, default=10.0)
    _add_view_args(check)
    check.set_defaults(func=cmd_check)

    snapshot = sub.add_parser("snapshot", help="Print the snapshot lma would send an arranger now")
    snapshot.add_argument("--pretty", action="store_true")
    _add_view_args(snapshot)
    snapshot.set_defaults(func=cmd_snapshot)

    serve_parser = sub.add_parser(
        "serve", help="Run a Python file's arrange(snapshot) function as an arranger"
    )
    serve_parser.add_argument("file", type=Path)
    serve_parser.set_defaults(func=cmd_serve)
