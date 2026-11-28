"""`lemonaid openclaw hook`: what lemonaid does when OpenClaw reports a turn's events."""

import argparse
import json
import sys

from ..config import load_config
from ..log import get_logger
from . import turn_end

_log = get_logger("openclaw.hook")


def _turn_end(data: dict) -> None:
    config = load_config()
    turn_end.settle(
        str(data["session_key"]),
        str(data.get("said") or ""),
        config.inbox.auto_read,
        config.rules,
        bool(data.get("failed")),
    )


def _run(args: argparse.Namespace) -> None:
    try:
        data = json.load(sys.stdin)
        _turn_end(data)
    except Exception:  # the command's top: log it, and let the caller go on
        _log.exception("openclaw hook %s failed", args.event)
        sys.exit(1)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "hook", help="handle a turn event, given as JSON on stdin (for lemonaid's own use)"
    )
    parser.add_argument("event", choices=["turn-end"])
    parser.set_defaults(func=_run)
