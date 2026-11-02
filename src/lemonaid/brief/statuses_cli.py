"""`lemonaid brief statuses`: the configured status words and how lemonaid treats each."""

import argparse
import json

from .. import config
from . import status_guide


def _cmd_statuses(args: argparse.Namespace) -> None:
    configured = config.brief_statuses()
    if args.json:
        print(json.dumps({"statuses": [s._asdict() for s in configured]}, ensure_ascii=False))
        return

    print(status_guide.guide(configured), end="")


def add_parser(brief_subparsers: argparse._SubParsersAction) -> None:
    parser = brief_subparsers.add_parser(
        "statuses", help="The Status words you can set, most urgent first, and when to use each"
    )
    parser.add_argument("--json", action="store_true", help="Every field of each status")
    parser.set_defaults(func=_cmd_statuses)
