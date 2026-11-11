"""`lemonaid github notifications`: list, show and mark read your GitHub notifications.

`list` prints your unread notification threads, each with what triage needs: the PR or
issue's state, author, draft and merge state, your latest review, the latest commit, and
`acted`, whether your account wrote an unsigned review or comment after the thread's
latest activity. `show <id>` prints one thread, read or not. `read <id>...` marks threads
read, the only command here that changes anything on GitHub. `--json` is for lemons.

    lemonaid github notifications list --json
    lemonaid github notifications show 1234567890
    lemonaid github notifications read 1234567890 1234567891
"""

import argparse
import json
import sys
from collections import abc

from . import notification_details, notifications, reviews_cli


def _line(d: notification_details.Details) -> str:
    state = "merged" if d.get("merged") else d.get("state") or "-"
    where = f"{d['repo']}#{d['number']}" if "number" in d else d["repo"]
    flags = "".join([" draft" if d.get("draft") else "", " acted" if d.get("acted") else ""])
    url = d.get("html_url") or d["type"]
    return f'{d["thread_id"]}  {d["reason"]:<16} {where}  {state}{flags}  "{d["title"]}"  {url}'


def _print(details: abc.Sequence[notification_details.Details], as_json: bool) -> None:
    if as_json:
        print(json.dumps(list(details), indent=2))
    else:
        print("\n".join(_line(d) for d in details) or "no unread notifications")


def _list(a: argparse.Namespace) -> int:
    threads = notifications.fetch(unread=True)
    if threads is None:
        print("cannot read GitHub notifications", file=sys.stderr)
        return 1

    kept = [t for t in threads if notifications.in_scope(t.repo, a.scope)]
    _print(notification_details.describe(kept), a.json)
    return 0


def _show(a: argparse.Namespace) -> int:
    found = notifications.thread(a.thread_id)
    if found is None:
        print(f"cannot read notification thread {a.thread_id}", file=sys.stderr)
        return 1

    _print(notification_details.describe([found]), a.json)
    return 0


def _read(a: argparse.Namespace) -> int:
    failed = [i for i in a.thread_ids if not notifications.mark_read(i)]
    for i in a.thread_ids:
        print(f"{'failed' if i in failed else 'read'} {i}")
    return 1 if failed else 0


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    github = subparsers.add_parser("github", help="Work with your GitHub account")
    github_sub = github.add_subparsers(dest="github_command", required=True)
    ap = github_sub.add_parser(
        "notifications",
        help="List, show and mark read your GitHub notifications",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="notifications_command", required=True)

    listing = sub.add_parser("list", help="Your unread notification threads, with details")
    listing.add_argument(
        "--scope",
        type=reviews_cli.scope_qualifier,
        action="append",
        default=[],
        metavar="QUALIFIER",
        help="limit to repos: org:NAME, user:NAME or repo:OWNER/NAME (repeatable)",
    )
    listing.add_argument("--json", action="store_true", help="print JSON")
    listing.set_defaults(func=lambda a: sys.exit(_list(a)))

    show = sub.add_parser("show", help="One notification thread, read or not, with details")
    show.add_argument("thread_id")
    show.add_argument("--json", action="store_true", help="print JSON")
    show.set_defaults(func=lambda a: sys.exit(_show(a)))

    read = sub.add_parser("read", help="Mark notification threads read")
    read.add_argument("thread_ids", nargs="+", metavar="THREAD_ID")
    read.set_defaults(func=lambda a: sys.exit(_read(a)))
