"""Move one attached lemon into another place, resuming its native session there."""

import argparse
import json
import sys
from pathlib import Path

from ...audit import events
from ...brief import lemon
from ...config import Config, PlaceRoot, load_config
from ...inbox import db
from ..restart import state
from . import coordinator, destination, planning


def _root(config: Config, given: str, cwd: str) -> PlaceRoot | None:
    if not given:
        return config.places.namespaced_root_for(cwd)

    root = config.places.root_for(Path(given).expanduser())
    if root is None:
        raise ValueError(f"No places root configured for {given}")

    return root


def _plan(args: argparse.Namespace) -> dict:
    config = load_config()
    with db.connect() as conn:
        row = lemon.attachment(conn, args.lemon, claim_pending=False).notification
    if row is None:
        raise ValueError(f"{args.lemon} has no session recorded, so there is nothing to move")

    to = destination.resolve(
        args.destination,
        _root(config, args.root or "", str(row.metadata.get("cwd") or "")),
        row.metadata,
        row.switch_source,
        config,
        acquire=not args.dry_run,
    )
    with db.connect() as conn:
        return planning.build(conn, args.lemon, to, config, args.force)


def _print(result: dict) -> None:
    plan = result["plan"]
    to = plan["destination"]
    workspace = f" ({to['workspace']})" if to["workspace"] else ""
    print(f"{plan['lemon_id']} -> {to['directory']}{workspace}: {result['phase']}")
    if token := result.get("token"):
        print(f"lemonaid lemon move --status {token}")
    if left := result.get("left_behind"):
        print(left)
    if result.get("error"):
        print(result["error"])


def _cmd(args: argparse.Namespace) -> None:
    try:
        if args.status:
            result = state.get(args.status)
        else:
            if not args.lemon or not args.destination:
                raise ValueError("Name a lemon and a destination, or use --status OPERATION_ID")
            plan = _plan(args)
            if args.dry_run:
                result = {"phase": "dry-run", "plan": plan}
            else:
                token = state.reserve(plan)
                try:
                    coordinator.spawn(token)
                except OSError as error:
                    state.update(token, "failed", error=str(error))
                    raise
                events.record(
                    "lemon-move",
                    plan["lemon_id"],
                    "forced" if args.force else "",
                    token=token,
                    claude_trust=plan["claude_trust"],
                    **{"from": plan["from"]["cwd"], "to": plan["destination"]["directory"]},
                )
                result = state.get(token)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            _print(result)
    except (LookupError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "move",
        help="Stop a lemon and resume the same conversation in another place",
        description="Move a live Claude or Codex lemon into another place: stop it, resume "
        "the same native session in a new window of the place's workspace, and close its old "
        "pane when only a shell is left there. Its Lemon-ID, brief, parent, groups and "
        "subscriptions stay as they are. DESTINATION is a place key, acquired through the "
        "root's hooks when missing, or an existing directory starting with / ~ or .",
    )
    parser.add_argument("lemon", nargs="?", help="A Lemon-ID, channel, or attached brief name")
    parser.add_argument("destination", nargs="?", help="A place key or a directory")
    parser.add_argument(
        "--root",
        help="The places root whose key DESTINATION is (default: the lemon's own root)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow interrupting a turn, as a lemon moving itself must; ownership checks still apply",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the checked plan without acquiring, stopping or starting anything",
    )
    parser.add_argument("--status", metavar="OPERATION_ID")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=_cmd)
