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
exits. `--ci` also reports passing CI once every check on the head finishes.
The head, state, reported comments and the rest are saved as cursors under the lemon's
Lemon-ID (or `--me` without a brief), so a waiter started later reports what changed after
the last one reported, and a first waiter starts from the PR as it is now. `--head`
overrides the saved head; with your own push recorded by lemonaid's hooks, it isn't needed.

One waiter per (PR, lemon) may run; a second exits at once, naming the first. So does
one started while the lemon's unified watcher (`watch --self`, or its push scout) runs: the
unified watcher shares the cursors and watches the brief's waiters, this one included.

    lemonaid watch pr --wait <number|url> [--repo owner/name] [--interval 60]
    lemonaid watch pr --wait <number> --comments --me "Author (MotorHoe)" --legacy Claude --head <sha> --once
    lemonaid watch pr --wait <number> --comments --me "Reviewer (SaltyEbb)" --head <sha> --codex-thread
    lemonaid watch pr --status <number|url> [--me "Author (MotorHoe)"]
"""

import argparse
import os
import pathlib
import re
import subprocess
import sys

from .. import config, pr_url, watch_config
from . import (
    brief_record,
    cursors,
    delivery,
    own_edits,
    own_pushes,
    pr_activity,
    pr_wait,
    registry,
    roles,
    wait_state,
    waiter_lock,
)


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


def _pr_ref(value: str) -> tuple[str, int]:
    """(owner/name, number) of a PR number or URL; the repo is "" for a bare number."""
    if value.isdigit():
        return "", int(value)

    if parsed := pr_url.parse(value):
        return parsed[0], int(parsed[1])

    raise argparse.ArgumentTypeError(f"not a PR number or a github.com pull request URL: {value!r}")


def run(a: argparse.Namespace, repo: str) -> int:
    a.codex_thread, problem = delivery.codex_thread(a.codex_thread)
    if problem:
        print(f"not started: {problem}")
        return 2

    pr = a.wait or a.status
    state_dir = a.state_dir or cursors.directory("pr", a.me, a.codex_thread)
    state_dir.mkdir(parents=True, exist_ok=True)
    stem = pr_wait.state_stem(state_dir, repo, pr, a.me if a.state_dir else "")
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

    unified = wait_state.lock_path(state_dir.parent.name)
    if not a.state_dir and waiter_lock.held(unified):
        print(
            f"not started: your unified watcher ({waiter_lock.lock_holder(unified)}) watches PR #{pr}"
            " with the same cursors and reports what this waiter would; it would never see an event"
        )
        lock.close()
        return 3

    writer = own_edits.writer_from_env(os.environ, a.codex_thread)
    if writer:
        own_pushes.register(own_edits.root(), writer)
    try:
        settings = config.load_config().watch
        filters = settings.pr
        with registry.watching(a, "pr", (f"{repo}#{pr}",), a.codex_thread, repo):
            pr_wait.wait(
                lambda: pr_activity.fetch(
                    repo,
                    pr,
                    (a.me, *a.legacy),
                    skip_outdated=filters.skip_outdated
                    if a.skip_outdated is None
                    else a.skip_outdated,
                    skip_resolved=filters.skip_resolved
                    if a.skip_resolved is None
                    else a.skip_resolved,
                ),
                pr,
                a.interval,
                a.head,
                a.comments,
                deliver,
                a.once or bool(a.codex_thread),
                stem,
                ci=a.ci,
                own_head=lambda head: own_pushes.is_own(own_edits.root(), writer, head),
                trusted=watch_config.logins_on(filters.trusted_commenters, pr_url.HOST),
                wake=roles.wake(a.role, settings.roles) if a.role else frozenset(roles.KINDS),
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

    url_repo, number = a.wait or a.status
    if url_repo and a.repo and url_repo.lower() != a.repo.lower():
        a.parser.error(f"--repo {a.repo} contradicts the PR URL's repo {url_repo}")

    a.repo = url_repo or a.repo
    a.wait, a.status = (number, None) if a.wait else (None, number)
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
    mode.add_argument("--wait", type=_pr_ref, metavar="PR", help="PR number or URL to watch")
    mode.add_argument(
        "--status",
        type=_pr_ref,
        metavar="PR",
        help="PR number or URL; report whether a waiter is running",
    )
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
    ap.add_argument(
        "--ci", action="store_true", help="also report completed CI, passing or failing"
    )
    ap.add_argument(
        "--role",
        choices=roles.ROLES,
        default="",
        help="wake only for the events this role needs (default: every event; under watch --self,"
        " worked out from the brief)",
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
        default=None,
        help="where the cursors and waiter lock live (default: this lemon's cursor directory)",
    )
    ap.set_defaults(func=_cmd, parser=ap)
