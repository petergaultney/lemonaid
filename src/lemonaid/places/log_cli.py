"""`place log`: who opened or tossed which place, from the audit log."""

import argparse
import json

from . import audit


def _line(e: dict) -> str:
    return " ".join(
        part
        for part in [
            e["at"],
            e["action"],
            e["outcome"],
            e.get("key") or "-",
            f"session={e['session']}" if e.get("session") else "",
            f"by={e['who']}",
            f"pid={e['pid']}",
            " ".join(e.get("flags", [])),
            f"- {e['reason']}" if e.get("reason") else "",
        ]
        if part
    )


def cmd_log(args: argparse.Namespace) -> None:
    found = audit.entries(args.limit, args.key)
    if args.json:
        print(json.dumps(found))
        return

    for e in found:
        print(_line(e))


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "log",
        help="Show who opened or tossed places (the audit log)",
        description="Prints the last events from the place audit log, oldest first: when, "
        "the action, the outcome, the place key, the tmux session, who ran it and its pid.",
    )
    parser.add_argument("key", nargs="?", default="", help="Only events for this key or session")
    parser.add_argument("-n", "--limit", type=int, default=20, help="How many (0 for all)")
    parser.add_argument("--json", action="store_true", help="Print the events as JSON")
    parser.set_defaults(func=cmd_log)
