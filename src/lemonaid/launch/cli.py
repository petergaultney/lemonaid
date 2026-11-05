"""`lemonaid lemon start`: start a lemon from config, beside the caller or in a tmux window."""

import argparse
import json
import sys

from ..config import load_config
from ..front_end import pick
from . import options, where, window


def _start(args: argparse.Namespace) -> tuple[dict, str]:
    """(JSON result, error). With no target, beside the caller in whichever terminal it is in."""
    session, colon, index = args.target.partition(":")
    if args.target and (not colon or not index.isdigit()):
        return {}, f"Name a window by its index: :WINDOW or SESSION:WINDOW, not {args.target!r}"

    beside = None if args.target else pick.around_caller()
    if not args.target and beside is None:
        return (
            {},
            "Not in tmux, WezTerm or cmux, so there is nowhere beside you: name SESSION:WINDOW",
        )

    own = window.own_session() if args.target and not session else ""
    if args.target and not session and not own:
        return {}, f"{args.target} means a window of your own tmux session, and this isn't in tmux"

    config = load_config()
    try:
        if options.preview(args, config.tmux_session):
            return {"preview": True}, ""
    except ValueError as error:
        return {}, str(error)

    if beside is None:
        return where.in_window(args, config, session or own, index)

    return beside.open_beside(args, config)


def _cmd_start(args: argparse.Namespace) -> None:
    result, error = _start(args)
    if result.get("preview"):
        return

    if args.json:
        print(json.dumps({**result, "error": error or None}))
    elif error:
        print(error, file=sys.stderr)
    else:
        print(f"started {result['harness']} in {result['where']}")

    if error:
        sys.exit(1)


def add_parser(lemon_subparsers: argparse._SubParsersAction) -> None:
    start = lemon_subparsers.add_parser(
        "start",
        help="Start a lemon beside you, or in a window of an existing tmux session",
        description="Runs a preset, harness executable, or legacy template's lemon line - the same one "
        "`place open` starts in its harness window - in window WINDOW of your own tmux "
        "session (:WINDOW) or of SESSION, in the session's directory. :WINDOW follows your "
        "session through renames, so a lemon starting a helper beside itself never needs its "
        "session's name. The window is made if it doesn't exist and respawned "
        "if its panes are dead; anything running there is refused. With no target, it starts "
        "beside you in the current directory: a new window of your own tmux session, a new "
        "tab in WezTerm, or a new workspace in cmux, and says where. Codex is "
        "started with its folder-trust and update prompts turned off, so the prompt reaches it.",
    )
    start.add_argument(
        "target",
        nargs="?",
        default="",
        metavar="[SESSION]:WINDOW",
        help="Where to start it: :4 is window 4 of your own tmux session; WINDOW is an index. "
        "Default: a new window or tab beside you",
    )
    options.add_arguments(start)
    start.add_argument(
        "--prompt",
        default="",
        help="The lemon's first prompt (with --brief, the default is to read the brief "
        "and do the work)",
    )
    start.add_argument(
        "--brief",
        default="",
        metavar="FILE",
        help="Attach this brief (a path, or a name in ~/.lemons/brief/) to the lemon once it starts",
    )
    start.add_argument(
        "--parent",
        default="",
        metavar="LEMON",
        help="Record LEMON (`self`, `parent` for your own parent, a Lemon-ID, channel, or brief) as the --brief lemon's parent",
    )
    start.add_argument(
        "--group",
        action="append",
        default=[],
        metavar="GROUP",
        help="Put the --brief lemon in this existing group (repeatable); default: its parent's",
    )
    start.add_argument(
        "--name", default="", help="Name the lemon's session once it starts (needs --brief)"
    )
    start.add_argument(
        "--no-check",
        action="store_true",
        help="Don't wait to check the pane for a startup dialog",
    )
    start.add_argument("--json", action="store_true", help="Print the result as JSON")
    start.set_defaults(func=_cmd_start)
    options.add_presets_parser(lemon_subparsers)
