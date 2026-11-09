"""`lemonaid watch reviews`: a blocking waiter on PRs that ask for your review.

Reports, once each, an open PR on which the `gh` user's review is newly requested, or
which is newly assigned to them without a request, naming its repo, number, title,
author and URL. A review request made to a team is not reported. `--scope` limits the
search with GitHub qualifiers such as `org:acme` or `repo:acme/widgets`. Read-only: it
never assigns, requests or comments.

Makes one GraphQL call per interval, shared by every waiter on the machine with the same
scope. The current PRs are saved as a cursor under the lemon's Lemon-ID (or `--me`
without a brief), so a first waiter takes the PRs asking for review now as already seen
(`--backlog` reports them instead) and a later one reports what changed since the last.

By default prints one line per event and never exits on its own. With `--once`, prints
the first event and exits. With `--codex-thread`, queues the first event into that Codex
thread and exits. One waiter per (scope, lemon) may run.

    lemonaid watch reviews --wait --scope org:acme --once
    lemonaid watch reviews --status --scope org:acme
"""

import argparse
import pathlib
import re
import sys
import time

from . import brief_record, cursors, delivery, registry, review_events, review_requests, waiter_lock


def _scope(value: str) -> str:
    if not re.fullmatch(r"(org|user|repo):[\w.-]+(/[\w.-]+)?", value):
        raise argparse.ArgumentTypeError(
            f"not a scope: {value!r} (use org:NAME, user:NAME or repo:OWNER/NAME)"
        )

    return value


def target(scope: list[str]) -> tuple[str, ...]:
    """The subscription target: `@me`, then the scope qualifiers in a stable order."""
    return ("@me", *sorted({s.lower() for s in scope}))


def run(a: argparse.Namespace) -> int:
    a.codex_thread, problem = delivery.codex_thread(a.codex_thread)
    if problem:
        print(f"not started: {problem}")
        return 2

    scope = target(a.scope)[1:]
    state_dir = a.state_dir or cursors.directory("reviews", a.me, a.codex_thread)
    state_dir.mkdir(parents=True, exist_ok=True)
    stem = review_events.state_stem(state_dir, scope, a.me if a.state_dir else "")
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
            f"not started: a review-request waiter as {a.me or '(no --me)'} is already running ({waiter_lock.lock_holder(lock_path)})"
        )
        return 3

    if a.codex_thread:
        problem = delivery.codex_setup_problem()
        deliver = delivery.to_codex(
            a.codex_thread,
            "lemonaid watch reviews",
            "Handle the review request, then rearm the waiter.",
        )
    else:
        problem, deliver = "", delivery.to_stdout
    if problem:
        print(f"not started: {problem}")
        return 2

    if error := brief_record.record(a, "reviews", a.codex_thread):
        print(f"not started: could not record waiter: {error}")
        lock.close()
        return 2

    once = a.once or bool(a.codex_thread)
    try:
        with registry.watching(a, "reviews", target(a.scope), a.codex_thread):
            while True:
                if (prs := review_requests.fetch(scope, a.interval)) is not None and (
                    review_events.poll(stem, prs, deliver, a.backlog) and once
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
        "reviews",
        help="Wait for PRs that request your review or are assigned to you",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--wait", action="store_true", help="wait for review requests")
    mode.add_argument(
        "--status", action="store_true", help="report whether a waiter for this scope is running"
    )
    ap.add_argument(
        "--scope",
        type=_scope,
        action="append",
        default=[],
        metavar="QUALIFIER",
        help="limit the search: org:NAME, user:NAME or repo:OWNER/NAME (repeatable)",
    )
    ap.add_argument(
        "--backlog",
        action="store_true",
        help="on the first poll, report the PRs already asking for review",
    )
    ap.add_argument("--interval", type=float, default=180.0, help="seconds between gh calls")
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
