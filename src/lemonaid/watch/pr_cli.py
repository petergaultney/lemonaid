"""`lemonaid watch pr`: a blocking waiter on one GitHub PR.

Reports when the PR's head commit moves, its state changes (OPEN -> MERGED / CLOSED), it
is marked ready for review or back to draft, or its review decision changes; and with
`--comments` also when someone else's comment appears in any review thread (including
outdated and resolved threads), a submitted review's body, or the PR conversation, and when the PR
conflicts with its base or its CI fails. `--comments` is the author's mode, so only the
author is woken to fix those. A comment is your own, and never reported, when it starts
with 🍋 followed by your `--me` signature or a `--legacy` one and a colon:
`🍋 Author (MotorHoe): done`. Other lemons' comments, signed or not, are reported. Makes one GraphQL call per interval through `gh`.

By default prints one line per event and never exits on its own. With `--once`, prints
the first event and exits, so a Claude background Bash task wakes its session once on
completion. With `--codex-thread`, queues the first event into that Codex thread and
exits. In both one-shot modes the woken turn handles the event and starts a fresh waiter
with `--head <new sha>`, so a push between the event and the rearm is still reported.

One waiter per (PR, --me) may run; a second exits at once, naming the first.

    lemonaid watch pr --wait <number> [--repo owner/name] [--interval 60]
    lemonaid watch pr --wait <number> --comments --me "Author (MotorHoe)" --legacy Claude --head <sha> --once
    lemonaid watch pr --wait <number> --comments --me "Reviewer (SaltyEbb)" --head <sha> --codex-thread
    lemonaid watch pr --status <number> [--me "Author (MotorHoe)"]
"""

import argparse
import pathlib
import re
import subprocess
import sys

from .. import config
from . import brief_record, delivery, pr_activity, pr_wait, waiter_lock


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


def _sha(value: str) -> str:
    """A full or abbreviated commit SHA, lowercased; shorter than 7 could match a later push.

    "" (no --head) passes, since argparse runs the default through this too.
    """
    if value and not re.fullmatch(r"[0-9a-fA-F]{7,40}", value):
        raise argparse.ArgumentTypeError(f"not a commit SHA of 7 to 40 hex digits: {value!r}")
    return value.lower()


def run(a: argparse.Namespace, repo: str) -> int:
    a.codex_thread, problem = delivery.codex_thread(a.codex_thread)
    if problem:
        print(f"not started: {problem}")
        return 2

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

    if error := brief_record.record(a, "pr", a.codex_thread, repo=repo):
        print(f"not started: could not record waiter: {error}")
        lock.close()
        return 2

    try:
        filters = config.load_config().watch.pr
        pr_wait.wait(
            lambda: pr_activity.fetch(
                repo,
                pr,
                (a.me, *a.legacy),
                skip_outdated=filters.skip_outdated if a.skip_outdated is None else a.skip_outdated,
                skip_resolved=filters.skip_resolved if a.skip_resolved is None else a.skip_resolved,
            ),
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
        help="Wait for pushes, state and review changes, and others' comments on a GitHub PR",
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
        "--head",
        type=_sha,
        default="",
        metavar="SHA",
        help="head already handled, full or abbreviated (7+ digits); report any other head",
    )
    ap.add_argument(
        "--comments",
        action="store_true",
        help="also report new human review and conversation comments, a conflict with the base, and failed CI",
    )
    for kind in ("outdated", "resolved"):
        ap.add_argument(
            f"--skip-{kind}",
            action=argparse.BooleanOptionalAction,
            default=None,
            help=f"skip {kind} review threads (default: [watch.pr] skip_{kind}, false if unset)",
        )
    ap.add_argument(
        "--me",
        default="",
        help="the signature you put after 🍋 in your comments, e.g. 'Author (MotorHoe)'; required with --comments",
    )
    ap.add_argument(
        "--legacy",
        action="append",
        default=[],
        metavar="NAME",
        help="another signature whose comments count as yours, e.g. an old one (repeatable)",
    )
    ap.add_argument("--once", action="store_true", help="print the first event and exit")
    delivery.add_codex_thread_argument(ap)
    ap.add_argument(
        "--state-dir",
        type=pathlib.Path,
        default=pr_wait.default_state_dir(),
        help="where reported comments and waiter locks live (default: $TMPDIR/watch-pr)",
    )
    ap.set_defaults(func=_cmd, parser=ap)
