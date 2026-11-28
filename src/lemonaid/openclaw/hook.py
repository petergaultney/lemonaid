"""`lemonaid openclaw hook`: what lemonaid does when OpenClaw reports a turn's events.

Lemonaid's OpenClaw plugin runs it for each event, with the event as JSON on stdin, as Claude
Code and Codex run `lemonaid hooks`. `lemonaid openclaw observe` runs `turn-end` too, where no
plugin reports turns.
"""

import argparse
import json
import sys
import time

from ..config import load_config
from ..hooks import own_change
from ..inbox import db
from ..log import get_logger
from ..watch import own_edits
from . import failures, plugin_install, run_records, turn_end

_log = get_logger("openclaw.hook")


def _turn(data: dict) -> None:
    with db.connect() as conn:
        run_records.running(conn, data["session_key"], str(data["run"]), float(data["at"]))


def _turn_end(data: dict) -> None:
    key, failed = str(data["session_key"]), bool(data.get("failed"))
    if "at" in data:  # from the plugin; the observer has recorded it already
        run, at = str(data.get("run") or ""), float(data["at"])
        if failed:
            failures.record(key, run, int(at * 1000), str(data.get("error") or ""))
        with db.connect() as conn:
            if not run_records.ended(conn, key, run, at):
                _log.info("ignoring %s's end of an older turn, run %r", key, run)
                return
    config = load_config()
    turn_end.settle(key, str(data.get("said") or ""), config.inbox.auto_read, config.rules, failed)


def _tool(data: dict) -> None:
    """Exits 2, with the reason on stderr, for a tool call that must not run."""
    call = {**data, "session_id": data["session_key"]}
    if reason := own_change.refusal(call):
        print(reason, file=sys.stderr)
        sys.exit(2)

    own_change.record(call, "openclaw", own_edits.root())


def _gateway_start(data: dict) -> None:
    with db.connect() as conn:
        run_records.all_ended(conn, float(data.get("at") or time.time()))


_EVENTS = {
    "turn": _turn,
    "turn-end": _turn_end,
    "tool": _tool,
    "gateway-start": _gateway_start,
}


def _run(args: argparse.Namespace) -> None:
    if args.plugin_version:
        plugin_install.note_version(args.plugin_version)
    try:
        _EVENTS[args.event](json.load(sys.stdin))
    except SystemExit:
        raise
    except Exception:  # the command's top: log it, and let the caller go on
        _log.exception("openclaw hook %s failed", args.event)
        sys.exit(1)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "hook", help="handle an OpenClaw event, given as JSON on stdin (for lemonaid's own use)"
    )
    parser.add_argument("event", choices=sorted(_EVENTS))
    parser.add_argument(
        "--plugin-version", default="", help="the version that installed the plugin"
    )
    parser.set_defaults(func=_run)
