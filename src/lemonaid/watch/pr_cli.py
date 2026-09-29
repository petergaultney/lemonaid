"""`lemonaid watch pr`: a blocking waiter on one GitHub PR.

Reports when the PR's head commit moves, its state changes (OPEN -> MERGED / CLOSED), it
is marked ready for review or back to draft, or its review decision changes; and with
`--comments` also when a human comment appears in an unresolved, non-outdated review
thread, in a submitted review's body, or in the PR conversation. Makes one GraphQL call
per interval through `gh`.

By default prints one line per event and never exits on its own. With `--once`, prints
the first event and exits, so a Claude background Bash task wakes its session once on
completion. With `--codex-thread`, queues the first event into that Codex thread and
exits. In both one-shot modes the woken turn handles the event and starts a fresh waiter
with `--head <new sha>`, so a push between the event and the rearm is still reported.

One waiter per (PR, --me) may run; a second exits at once, naming the first. Flags,
state files and locks match the standalone watch-pr.py, so either can replace the other.

    lemonaid watch pr --wait <number> [--repo owner/name] [--interval 60]
    lemonaid watch pr --wait <number> --comments --me Pliny --head <sha> --once
    lemonaid watch pr --wait <number> --comments --me Pliny --head <sha> --codex-thread "$CODEX_THREAD_ID"
    lemonaid watch pr --status <number> [--me Pliny]
"""

import argparse
import pathlib
import subprocess
import sys

from . import delivery, pr_activity, pr_wait, waiter_lock


def _repo_name(repo: str) -> str:
    """owner/name of --repo, or of the repo of the current directory; "" if gh can't tell."""
    r = subprocess.run(
        [
            "gh",
            "repo",
            "view",
            *([repo] if repo else []),
            "--json",
            "nameWithOwner",
            "--jq",
            ".nameWithOwner",
        ],
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() or repo


def run(a: argparse.Namespace, repo: str) -> int:
    a.state_dir.mkdir(parents=True, exist_ok=True)
    pr = a.wait or a.status
    stem = pr_wait.state_stem(a.state_dir, repo, pr, a.me)
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
            f"not started: a waiter for PR #{pr} as {a.me or '(no --me)'} is already running ({waiter_lock.lock_holder(lock_path)})"
        )
        return 3

    if a.codex_thread:
        problem = delivery.codex_setup_problem()
        deliver = delivery.to_codex(
            a.codex_thread,
            "watch-pr",
            "Use $watch-pr to handle it, then rearm the waiter unless the PR is closed.",
        )
    else:
        problem, deliver = "", delivery.to_stdout
    if problem:
        print(f"not started: {problem}")
        return 2

    try:
        pr_wait.wait(
            lambda: pr_activity.fetch(repo, pr),
            pr,
            a.interval,
            a.head,
            a.comments,
            deliver,
            a.once or bool(a.codex_thread),
            stem,
        )
    except KeyboardInterrupt:
        pass
    except delivery.Failed as e:
        print(f"{e}; rearm with --head set to the last head you handled")
        return 1
    return 0


def _cmd(a: argparse.Namespace) -> None:
    if a.comments and not a.me:
        a.parser.error("--comments needs --me")

    repo = _repo_name(a.repo)
    if not repo:
        a.parser.error("cannot tell which repo; pass --repo owner/name")

    sys.exit(run(a, repo))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "pr",
        help="Wait for pushes, state and review changes, and human comments on a GitHub PR",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--wait", type=int, metavar="PR", help="PR number to watch")
    mode.add_argument("--status", type=int, metavar="PR", help="report whether a waiter is running")
    ap.add_argument(
        "--repo", default="", help="owner/name; default is the repo of the current directory"
    )
    ap.add_argument("--interval", type=float, default=60.0, help="seconds between gh calls")
    ap.add_argument(
        "--head", default="", metavar="SHA", help="head already handled; report any other head"
    )
    ap.add_argument(
        "--comments",
        action="store_true",
        help="also report new human review and conversation comments",
    )
    ap.add_argument("--me", default="", help="your lemon name; required with --comments")
    ap.add_argument("--once", action="store_true", help="print the first event and exit")
    ap.add_argument(
        "--codex-thread",
        default="",
        metavar="THREAD_ID",
        help="queue one event into this Codex thread and exit instead of printing events forever",
    )
    ap.add_argument(
        "--state-dir",
        type=pathlib.Path,
        default=pr_wait.default_state_dir(),
        help="where reported comments and waiter locks live (default: $TMPDIR/watch-pr)",
    )
    ap.set_defaults(func=_cmd, parser=ap)
