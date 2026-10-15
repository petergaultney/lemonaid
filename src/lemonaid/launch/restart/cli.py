"""Restart one attached lemon in its reserved tmux pane."""

import argparse
import json
import shlex
import sys

from ...config import load_config
from ...inbox import db
from . import coordinator, environment, planning, state


def _report(operation: dict) -> dict:
    plan = operation["plan"]
    recovery_error = ""
    try:
        environment.validate(plan["settings"])
        resume = shlex.join(
            [
                *environment.prefix(
                    {**plan["settings"]["environment"], "LEMONAID_RESTART_TOKEN": None}
                ),
                *plan["argv"],
            ]
        )
    except ValueError as error:
        resume, recovery_error = "", str(error)
    return {
        "operation_id": operation["token"],
        "lemon": plan["lemon_id"],
        "channel": plan["channel"],
        "pane": plan["pane"]["pane"],
        "socket": plan["pane"]["socket"],
        "phase": operation["phase"],
        "error": operation["error"],
        "deadline": operation["deadline"],
        "resume_command": resume,
        "recovery_error": recovery_error,
        "status_command": f"lemonaid lemon restart --status {operation['token']}",
    }


def _cmd(args: argparse.Namespace) -> None:
    try:
        with db.connect() as conn:
            if args.status:
                result = _report(state.get(conn, args.status))
            else:
                if not args.lemon:
                    raise ValueError("Name one lemon, or use --status OPERATION_ID")
                plan = planning.build(conn, args.lemon, load_config(), args.force)
                if args.dry_run:
                    result = {"phase": "dry-run", **plan}
                else:
                    token = state.reserve(conn, plan)
                    try:
                        coordinator.spawn(token)
                    except OSError as error:
                        state.update(conn, token, "failed", error=str(error))
                        raise
                    result = _report(state.get(conn, token))
        if args.force and not args.status:
            print(
                "Warning: --force may discard input or interrupt tools with external effects.",
                file=sys.stderr,
            )
        print(
            json.dumps(result, indent=2)
            if args.json
            else (
                f"{result.get('lemon', result.get('lemon_id'))}: {result['phase']}"
                + (
                    f"; operation {result['operation_id']}\n{result['status_command']}"
                    if "operation_id" in result
                    else ""
                )
                + (f"\n{result['error']}" if result.get("error") else "")
            )
        )
    except (LookupError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("restart", help="Restart one live lemon in its own tmux pane")
    parser.add_argument("lemon", nargs="?", help="Lemon-ID, channel, or attached brief name")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Interrupt a turn or discard input; ownership checks still apply",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Check and print the plan without stopping anything"
    )
    parser.add_argument(
        "--status",
        metavar="OPERATION_ID",
        help="Report a saved operation without replaying actions",
    )
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=_cmd)
