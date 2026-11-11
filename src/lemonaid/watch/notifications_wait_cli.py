"""`lemonaid watch notifications`: a blocking waiter on your unread GitHub notifications.

Wakes a lemon, at most once per `--every` minutes (30 by default), with the unread
notification threads that are new or have new activity since it was last told, one line
each, so it can triage them with `lemonaid github notifications`. `--scope` limits it to
repos by `org:acme`, `user:sam` or `repo:acme/widgets`. Read-only: it never marks a
notification read.

The cursor lives under the lemon's Lemon-ID (or `--me` without a brief), so a first
waiter takes current unread threads as seen (`--backlog` reports them instead).

By default prints one block per batch and never exits on its own. With `--once`, prints
the first batch and exits. With `--codex-thread`, queues the first batch into that Codex
thread and exits. One waiter per (scope, lemon) may run.

    lemonaid watch notifications --wait --every 60 --once
    lemonaid watch notifications --status
"""

import argparse
import pathlib
import sys
import time

from . import (
    brief_record,
    cursors,
    delivery,
    notification_events,
    registry,
    reviews_cli,
    waiter_lock,
)


def run(a: argparse.Namespace) -> int:
    a.codex_thread, problem = delivery.codex_thread(a.codex_thread)
    if problem:
        print(f"not started: {problem}")
        return 2

    scope = reviews_cli.target(a.scope)[1:]
    state_dir = a.state_dir or cursors.directory("notifications", a.me, a.codex_thread)
    state_dir.mkdir(parents=True, exist_ok=True)
    stem = notification_events.state_stem(state_dir, scope, a.me if a.state_dir else "")
    lock_path = stem.with_suffix(".lock")
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
            f"not started: a notification waiter as {a.me or '(no --me)'} is already running ({waiter_lock.lock_holder(lock_path)})"
        )
        return 3

    if a.codex_thread:
        problem = delivery.codex_setup_problem()
        deliver = delivery.to_codex(
            a.codex_thread,
            "lemonaid watch notifications",
            "Triage the notifications, then rearm the waiter.",
        )
    else:
        problem, deliver = "", delivery.to_stdout
    if problem:
        print(f"not started: {problem}")
        return 2

    if error := brief_record.record(a, "notifications", a.codex_thread):
        print(f"not started: could not record waiter: {error}")
        lock.close()
        return 2

    once = a.once or bool(a.codex_thread)
    try:
        with registry.watching(a, "notifications", reviews_cli.target(a.scope), a.codex_thread):
            while True:
                if notification_events.poll(stem, scope, deliver, a.backlog) and once:
                    return 0

                time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    except delivery.Failed as e:
        print(f"{e}; the change was not recorded and will be reported to the next waiter")
        return 1
    return 0


def _cmd(a: argparse.Namespace) -> None:
    sys.exit(run(a))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "notifications",
        help="Wait for new unread GitHub notifications, in batches",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--wait", action="store_true", help="wait for notifications")
    mode.add_argument(
        "--status", action="store_true", help="report whether a waiter for this scope is running"
    )
    ap.add_argument(
        "--scope",
        type=reviews_cli.scope_qualifier,
        action="append",
        default=[],
        metavar="QUALIFIER",
        help="limit to repos: org:NAME, user:NAME or repo:OWNER/NAME (repeatable)",
    )
    ap.add_argument(
        "--backlog",
        action="store_true",
        help="on the first poll, report the threads already unread",
    )
    ap.add_argument(
        "--every",
        dest="interval",
        type=lambda minutes: float(minutes) * 60,
        default=1800.0,
        metavar="MINUTES",
        help="minutes between batches (default 30)",
    )
    ap.add_argument("--me", default="", help="your lemon name, so two lemons' waiters stay apart")
    ap.add_argument("--once", action="store_true", help="print the first batch and exit")
    delivery.add_codex_thread_argument(ap)
    ap.add_argument(
        "--state-dir",
        type=pathlib.Path,
        default=None,
        help="where the cursors and waiter lock live (default: this lemon's cursor directory)",
    )
    ap.set_defaults(func=_cmd)
