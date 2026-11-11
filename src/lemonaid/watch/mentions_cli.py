"""`lemonaid watch mentions`: a blocking waiter on direct @mentions of you on PRs.

Reports, once each, a comment, review, inline review comment or new PR description that
writes `@<your gh login>`, naming the PR, who wrote it, where, its URL and its start. Team
mentions, comments by your own account (lemons post as you) and bots are not reported,
nor is a PR some live lemon already hears comments on. `--scope` limits it to repos by
`org:acme`, `user:sam` or `repo:acme/widgets`. Read-only: it never marks a notification
read.

Reads your GitHub notifications, including ones already read, every interval, and each
PR with new activity there. The cursor lives under the lemon's Lemon-ID (or `--me`
without a brief), so a first waiter takes current mentions as seen (`--backlog` reports
the last day's instead) and a later one reports what arrived since the last.

By default prints one block per event and never exits on its own. With `--once`, prints
the first event and exits. With `--codex-thread`, queues the first event into that Codex
thread and exits. One waiter per (scope, lemon) may run.

    lemonaid watch mentions --wait --scope org:acme --once
    lemonaid watch mentions --status --scope org:acme
"""

import argparse
import pathlib
import sys
import time

from . import (
    brief_record,
    cursors,
    delivery,
    mention_events,
    pr_poller,
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
    state_dir = a.state_dir or cursors.directory("mentions", a.me, a.codex_thread)
    state_dir.mkdir(parents=True, exist_ok=True)
    stem = mention_events.state_stem(state_dir, scope, a.me if a.state_dir else "")
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
            f"not started: a mention waiter as {a.me or '(no --me)'} is already running ({waiter_lock.lock_holder(lock_path)})"
        )
        return 3

    if a.codex_thread:
        problem = delivery.codex_setup_problem()
        deliver = delivery.to_codex(
            a.codex_thread,
            "lemonaid watch mentions",
            "Handle the mention, then rearm the waiter.",
        )
    else:
        problem, deliver = "", delivery.to_stdout
    if problem:
        print(f"not started: {problem}")
        return 2

    if error := brief_record.record(a, "mentions", a.codex_thread):
        print(f"not started: could not record waiter: {error}")
        lock.close()
        return 2

    once = a.once or bool(a.codex_thread)
    try:
        with registry.watching(a, "mentions", reviews_cli.target(a.scope), a.codex_thread):
            while True:
                if (
                    mention_events.poll(stem, scope, deliver, pr_poller.hears_comments, a.backlog)
                    and once
                ):
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
        "mentions",
        help="Wait for comments on PRs that @mention you",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--wait", action="store_true", help="wait for mentions")
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
        help="on the first poll, report the last day's mentions",
    )
    ap.add_argument("--interval", type=float, default=180.0, help="seconds between polls")
    ap.add_argument("--me", default="", help="your lemon name, so two lemons' waiters stay apart")
    ap.add_argument("--once", action="store_true", help="print the first event and exit")
    delivery.add_codex_thread_argument(ap)
    ap.add_argument(
        "--state-dir",
        type=pathlib.Path,
        default=None,
        help="where the cursors and waiter lock live (default: this lemon's cursor directory)",
    )
    ap.set_defaults(func=_cmd)
