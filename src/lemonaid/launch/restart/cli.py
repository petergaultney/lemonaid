"""Restart one attached lemon through its configured native resume command."""

import argparse
import json
import sys

from ...config import load_config
from ...inbox import db
from . import coordinator, planning, state


def _cmd(args: argparse.Namespace) -> None:
    try:
        if args.status:
            result = state.get(args.status)
        else:
            if not args.lemon:
                raise ValueError("Name one lemon, or use --status OPERATION_ID")
            with db.connect() as conn:
                plan = planning.build(conn, args.lemon, load_config(), args.force)
            if args.dry_run:
                result = {"phase": "dry-run", "plan": plan}
            else:
                token = state.reserve(plan)
                try:
                    coordinator.spawn(token)
                except OSError as error:
                    state.update(token, "failed", error=str(error))
                    raise
                result = state.get(token)
        result["resume_command"] = result["plan"]["line"]
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"{result['plan']['lemon_id']}: {result['phase']}")
            if token := result.get("token"):
                print(f"lemonaid lemon restart --status {token}")
            if result.get("error"):
                print(result["error"])
                print("Inspect the pane; resume manually with the saved command and environment.")
    except (LookupError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "restart", help="Stop and resume one lemon in the same tmux pane"
    )
    parser.add_argument("lemon", nargs="?")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow interrupting a turn; ownership checks still apply",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the checked resume plan without stopping anything",
    )
    parser.add_argument("--status", metavar="OPERATION_ID")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=_cmd)
