"""`lemonaid po-box list`: who has a PO box, so a teammate can address one."""

import argparse
import datetime
import sys

from ..config import load_config
from . import cards


def cmd_list(args: argparse.Namespace) -> None:
    config = load_config().po_box
    if config.root is None or not config.root.is_dir():
        print("PO boxes aren't set up: set [po-box] root to the shared folder", file=sys.stderr)
        raise SystemExit(1)

    now = datetime.datetime.now(datetime.UTC)
    for card in cards.everyone(config.root):
        if card.expired(now) and not args.all:
            continue

        expired = " (expired)" if card.expired(now) else ""
        print(f"{card.address}\t{card.area}\t{card.title}{expired}")


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "po-box",
        help="List the lemons with PO boxes in the shared folder",
        description="A lemon whose brief says `PO box: yes` has a PO box; send to one with "
        "`lemonaid tell <owner>/<lemon>`.",
    )
    commands = parser.add_subparsers(dest="po_box_command", required=True)
    listing = commands.add_parser("list", help="Print each PO box's address, area and title")
    listing.add_argument("--all", action="store_true", help="Include expired registrations")
    listing.set_defaults(func=cmd_list)
