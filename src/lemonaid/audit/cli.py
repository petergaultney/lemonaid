"""`lemonaid audit`: who archived, revived, edited, restarted or tossed what, and why."""

import argparse
import json

from . import events


def _line(e: dict) -> str:
    return " ".join(
        part
        for part in [
            e.get("at", ""),
            e.get("action", ""),
            e.get("outcome", ""),
            e.get("thing") or "-",
            f"by={e.get('who', 'unknown')}",
            f"via={e['via']}" if e.get("via") else "",
            f"pid={e['pid']}" if e.get("pid") else "",
            f"- {e['why']}" if e.get("why") else "",
        ]
        if part
    )


def _cmd(args: argparse.Namespace) -> None:
    found = events.entries(args.limit, args.by, args.thing)
    if args.json:
        print(json.dumps(found))
        return

    for e in found:
        print(_line(e))


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "audit",
        help="Show who archived, revived, edited, restarted or tossed what (the audit log)",
        description="Prints the last state-changing actions, oldest first: when, the action, "
        "what it acted on, who did it and how lemonaid knew (via env, tmux, tty, ppid, or "
        "code for lemonaid's own jobs), and why. Covers place opens and tosses too.",
    )
    parser.add_argument("--by", default="", help="Only actions by an actor matching this text")
    parser.add_argument(
        "--thing",
        default="",
        help="Only actions on something matching this text: a Lemon-ID, brief, channel, "
        "place key, session or directory",
    )
    parser.add_argument("-n", "--limit", type=int, default=20, help="How many (0 for all)")
    parser.add_argument("--json", action="store_true", help="Print the events as JSON")
    parser.set_defaults(func=_cmd)
