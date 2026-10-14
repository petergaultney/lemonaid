"""`lemonaid watch repo`: a blocking waiter on a whole GitHub repo's pull requests.

Reports a PR opened ready for review, a draft marked ready for review, a watched label
(`--label`) added to an open PR, and a seen PR closed or merged; with `--pushes`, also a
ready PR's head moving. With `--label`, only PRs carrying at least one of those labels are
reported; `--exclude-author` skips PRs by those logins. Each event names the PR's number,
title, author and head branch. Makes one GraphQL call per interval through `gh` (more for a
repo with over 100 open PRs).

By default prints one line per event and never exits on its own. With `--once`, prints
the first event and exits, so a Claude background Bash task wakes its session once on
completion. With `--codex-thread`, queues the first event into that Codex thread and exits.
The open PRs and their labels are saved as a cursor under the lemon's Lemon-ID (or `--me`
without a brief), so a first waiter takes the PRs open now as already seen and a later one
reports what changed since the last. One waiter per (repo, lemon) may run.

    lemonaid watch repo --wait owner/name [--label NAME ...] [--exclude-author LOGIN ...] --once
    lemonaid watch repo --wait owner/name --label needs-review --codex-thread
    lemonaid watch repo --status owner/name
"""

import argparse
import pathlib
import re
import sys
import time

from . import brief_record, cursors, delivery, registry, repo_activity, repo_events, waiter_lock


def _repo(value: str) -> str:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        raise argparse.ArgumentTypeError(f"not an owner/name repo: {value!r}")

    return value


def run(a: argparse.Namespace) -> int:
    a.codex_thread, problem = delivery.codex_thread(a.codex_thread)
    if problem:
        print(f"not started: {problem}")
        return 2

    repo = a.wait or a.status
    state_dir = a.state_dir or cursors.directory("repo", a.me, a.codex_thread)
    state_dir.mkdir(parents=True, exist_ok=True)
    stem = repo_events.state_stem(state_dir, repo, a.me if a.state_dir else "")
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
            f"not started: a waiter for {repo} as {a.me or '(no --me)'} is already running ({waiter_lock.lock_holder(lock_path)})"
        )
        return 3

    if a.codex_thread:
        problem = delivery.codex_setup_problem()
        deliver = delivery.to_codex(
            a.codex_thread,
            "lemonaid watch repo",
            "Handle the PR, then rearm the waiter.",
        )
    else:
        problem, deliver = "", delivery.to_stdout
    if problem:
        print(f"not started: {problem}")
        return 2

    if error := brief_record.record(a, "repo", a.codex_thread):
        print(f"not started: could not record waiter: {error}")
        lock.close()
        return 2

    once = a.once or bool(a.codex_thread)
    try:
        with registry.watching(a, "repo", (repo,), a.codex_thread):
            while True:
                if (prs := repo_activity.fetch(repo)) is not None and (
                    repo_events.poll(
                        stem,
                        repo,
                        prs,
                        deliver,
                        labels=a.label,
                        exclude_authors=a.exclude_author,
                        pushes=a.pushes,
                    )
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
        "repo",
        help="Wait for PRs opened or marked ready for review, or labeled, in a GitHub repo",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--wait", type=_repo, metavar="OWNER/NAME", help="repo to watch")
    mode.add_argument(
        "--status",
        type=_repo,
        metavar="OWNER/NAME",
        help="report whether a waiter for this repo is running",
    )
    ap.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="NAME",
        help="report only PRs carrying this label, and its being added (repeatable)",
    )
    ap.add_argument(
        "--exclude-author",
        action="append",
        default=[],
        metavar="LOGIN",
        help="skip PRs by this GitHub login (repeatable)",
    )
    ap.add_argument("--pushes", action="store_true", help="also report a ready PR's head moving")
    ap.add_argument("--interval", type=float, default=60.0, help="seconds between gh calls")
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
