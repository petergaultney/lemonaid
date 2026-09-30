"""`lemonaid lemon start`: start a lemon in a window of an existing session, from config."""

import argparse
import json
import sys

from ..config import load_config
from . import command, handoff, window


def _start(args: argparse.Namespace) -> tuple[dict, str]:
    """(JSON result, error)."""
    session, _, index = args.target.partition(":")
    if not session or not index.isdigit():
        return {}, f"Name a window by its index: SESSION:WINDOW, not {args.target!r}"

    config = load_config()
    windows = config.tmux_session.get_template(args.harness)
    if not windows:
        return {}, f"No tmux-session template {args.harness!r} in config"

    line = windows[command.template_window(config.tmux_session, windows)]
    if not line.strip():
        return {}, f"Tmux-session template {args.harness!r} has no harness command"

    directory = window.session_dir(session)
    if directory is None:
        return {}, f"No tmux session {session!r}"

    given, error = handoff.prepare(args.brief, args.parent, args.name)
    if error:
        return {}, error

    if given.brief and (error := command.unclaimable(line)):
        return {}, error

    pane, error = window.open_window(session, index, directory)
    if pane is None:
        return {}, error

    result = {
        "session": session,
        "window": index,
        "window_id": pane.window_id,
        "dir": str(directory),
        "harness": args.harness,
        "brief": str(given.brief) if given.brief else None,
        "lemon_id": given.link[0] if given.link else None,
        "parent": given.link[1] if given.link else None,
        "name": given.name or None,
    }
    handoff.complete(given, session, index, pane.window_id)
    if error := window.run(pane, command.harness_line(line, directory, args.prompt)):
        return result, error

    if not args.no_check and (dialog := window.startup_dialog(pane)):
        return result, f"The lemon in {session}:{index} is waiting at {dialog}"

    return result, ""


def _cmd_start(args: argparse.Namespace) -> None:
    result, error = _start(args)
    if args.json:
        print(json.dumps({**result, "error": error or None}))
    elif error:
        print(error, file=sys.stderr)
    else:
        print(f"started {args.harness} in {result['session']}:{result['window']}")

    if error:
        sys.exit(1)


def add_parser(lemon_subparsers: argparse._SubParsersAction) -> None:
    start = lemon_subparsers.add_parser(
        "start",
        help="Start a lemon in a window of an existing tmux session",
        description="Runs [tmux-session.templates].NAME's harness line - the same one "
        "`place open` starts in its harness window - in SESSION:WINDOW, in the "
        "session's directory. The window is made if it doesn't exist and respawned "
        "if its panes are dead; anything running there is refused. Codex is started "
        "with its folder-trust and update prompts turned off, so the prompt reaches it.",
    )
    start.add_argument(
        "target", metavar="SESSION:WINDOW", help="Where to start it; WINDOW is an index"
    )
    start.add_argument(
        "--harness",
        default="default",
        metavar="NAME",
        help="Use [tmux-session.templates].NAME (default: default)",
    )
    start.add_argument("--prompt", default="", help="The lemon's first prompt")
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
        help="Record LEMON (`self`, a Lemon-ID, channel, or brief) as the --brief lemon's parent",
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
