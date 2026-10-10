"""Wait for direct children to enter selected brief statuses.

The first run takes existing children as its baseline. Subsequent runs report changes
made between rearms, including newly linked children. Repeat --to STATUS to select
which destination statuses wake the parent (default: merge and done). Other status
changes and Needs-only changes advance the baseline without waking.
"""

import argparse
import pathlib
import sys
import time

from ..brief import lemon, store
from ..inbox import db
from . import brief_record, briefs_events, delivery, registry, waiter_lock

CHILD_TO = ("merge", "done")
_ORPHAN_TO = ("blocked", "alert", "merge", "approve", "review", "done")


def _wait(
    w: briefs_events.BriefsWatch, deliver: delivery.Deliver, once: bool, interval: float
) -> None:
    while True:
        if briefs_events.poll(w, deliver) and once:
            return
        time.sleep(interval)


def run(a: argparse.Namespace) -> int:
    thread, problem = delivery.codex_thread(a.codex_thread)
    if problem:
        print(f"not started: {problem}")
        return 2
    try:
        with db.connect() as conn:
            parent = (
                lemon.own_id(conn, a.channel or "") if a.use_self else lemon.lemon_id(conn, a.lemon)
            )
    except (LookupError, ValueError, store.ChangedUnderneath) as error:
        print(f"not started: {error}")
        return 2

    a.state_dir.mkdir(parents=True, exist_ok=True)
    to = frozenset(a.to or (_ORPHAN_TO if a.orphans else CHILD_TO))
    lock_path = briefs_events.state_stem(a.state_dir, parent, a.me, to, a.orphans).with_suffix(
        ".lock"
    )
    if a.status:
        running = waiter_lock.held(lock_path)
        print(
            f"waiter running: {waiter_lock.lock_holder(lock_path)}"
            if running
            else "no waiter running"
        )
        return 0 if running else 1

    lock = waiter_lock.acquire(lock_path)
    if lock is None:
        print(
            f"not started: a waiter for {parent}'s children is already running ({waiter_lock.lock_holder(lock_path)})"
        )
        return 3
    try:
        if thread and (problem := delivery.codex_setup_problem()):
            print(f"not started: {problem}")
            return 2
        deliver = (
            delivery.to_codex(
                thread,
                "lemonaid watch briefs",
                "Read the changed children's briefs, handle the changes, then rearm the waiter.",
            )
            if thread
            else delivery.to_stdout
        )
        if error := brief_record.record(a, "briefs", thread):
            print(f"not started: could not record waiter: {error}")
            return 2
        with registry.watching(a, "briefs", (parent,), thread):
            _wait(
                briefs_events.open_watch(a.state_dir, parent, a.me, a.quiet, to, a.orphans),
                deliver,
                a.once or bool(thread),
                a.interval,
            )
    except KeyboardInterrupt:
        pass
    except delivery.Failed as error:
        print(f"{error}; the change was not recorded and will be reported to the next waiter")
        return 1
    finally:
        lock.close()
    return 0


def _cmd(a: argparse.Namespace) -> None:
    sys.exit(run(a))


def _target(value: str) -> str:
    if value in store.RETIRED:
        raise argparse.ArgumentTypeError(
            f"{value!r} is no longer a brief status: a child without one shows active or idle,"
            " and never wakes this waiter. Drop it, or name the statuses it moves to"
        )

    if value not in store.STATES:
        raise argparse.ArgumentTypeError(f"{value!r} is not one of {', '.join(store.STATES)}")

    return value


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "briefs", help="Wait for children to enter selected brief statuses", description=__doc__
    )
    ap.add_argument(
        "--children",
        action="store_true",
        required=True,
        help="watch direct children through Lemon-ID parent links",
    )
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--self", dest="use_self", action="store_true", help="watch this lemon's children"
    )
    target.add_argument("lemon", nargs="?", help="parent Lemon-ID, channel, or brief name")
    ap.add_argument(
        "--to",
        action="append",
        type=_target,
        default=[],
        metavar="STATUS",
        help="wake only on entry into this status (repeatable; default: merge, done; with "
        "--orphans: blocked, alert, merge, approve, review, done)",
    )
    ap.add_argument(
        "--orphans",
        action="store_true",
        help="also watch briefs no live lemon owns (no parent, or a parent whose session is gone); "
        "their Needs asks wake too, and --to defaults to blocked, alert, merge, approve, review, done",
    )
    ap.add_argument("--channel", help="override self detection")
    ap.add_argument("--me", default="", help="watcher name, to keep independent watchers apart")
    ap.add_argument("--status", action="store_true", help="check whether this waiter is running")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between reads")
    ap.add_argument(
        "--quiet",
        type=float,
        default=2.0,
        help="seconds with no further selected-state changes before delivery",
    )
    ap.add_argument("--once", action="store_true", help="print the first batch and exit")
    delivery.add_codex_thread_argument(ap)
    ap.add_argument(
        "--state-dir",
        type=pathlib.Path,
        default=briefs_events.default_state_dir(),
        help="reported state and locks (default: $TMPDIR/lemonaid-watch-briefs)",
    )
    ap.set_defaults(func=_cmd)
