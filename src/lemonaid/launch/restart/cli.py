"""Inspect whether one attached lemon can be restarted in its tmux pane."""

import argparse
import json
import sys

from ...config import load_config
from ...inbox import db
from . import planning


def _cmd(args: argparse.Namespace) -> None:
    try:
        if not args.dry_run:
            raise ValueError("This preflight command requires --dry-run")

        with db.connect() as conn:
            plan = planning.build(conn, args.lemon, load_config(), args.force)
        print(
            json.dumps({"phase": "dry-run", **plan}, indent=2)
            if args.json
            else f"{plan['lemon_id']}: restart preflight passed in {plan['pane']['pane']}"
        )
    except (LookupError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("restart", help="Inspect one lemon's restart plan")
    parser.add_argument("lemon", help="Lemon-ID, channel, or attached brief name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force", action="store_true", help="Allow interrupted turns or discarded input"
    )
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=_cmd)
