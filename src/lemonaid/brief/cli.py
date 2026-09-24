"""CLI for showing where a lemon's work stands, from its brief."""

import argparse
import sys
import time
from pathlib import Path

from . import popup, session, status


def _directory(target: str, dir_arg: str) -> Path:
    if dir_arg:
        return Path(dir_arg)

    directory = session.session_dir(target) if target else None
    if directory is None:
        print(
            f"No tmux session '{target}'."
            if target
            else "Not in tmux; name a session or pass --dir.",
            file=sys.stderr,
        )
        sys.exit(1)

    return directory


def cmd_show(args: argparse.Namespace) -> None:
    target = args.session or ("" if args.dir else session.current_session())
    directory = _directory(target, args.dir)
    names = [*session.names(target), *args.name] if target else args.name
    if args.popup:
        popup.open_popup(directory, names, title=target or directory.name)
        return

    markdown = status.render(status.notes_dir(directory), names, time.time())
    if args.page:
        popup.page(markdown)
    else:
        print(markdown)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    brief_parser = subparsers.add_parser(
        "brief",
        help="Where a lemon's work stands, from its brief",
        description="A brief is .z/brief.md, or .z/brief-<name>.md when several "
        "lemons share a directory. Its Status line and `## Now` section are what the "
        "worker keeps current.",
    )
    brief_subparsers = brief_parser.add_subparsers(dest="brief_command")

    show_parser = brief_subparsers.add_parser(
        "show",
        help="Print a session's Status and Now, or show them in a popup",
        description="Finds the session's directory from tmux and shows its brief: the "
        "one named for the session's LEMON_NAME or session name if there is one, "
        "otherwise every brief there, newest first. Falls back to .z/state.md when "
        "there is no brief.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    show_parser.add_argument(
        "session", nargs="?", default="", help="tmux session (default: the current one)"
    )
    show_parser.add_argument(
        "--dir", default="", help="Read this directory instead of asking tmux for one"
    )
    show_parser.add_argument(
        "--name",
        action="append",
        default=[],
        help="Also prefer .z/brief-NAME.md (repeatable)",
    )
    mode = show_parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--popup", action="store_true", help="Show it in a tmux popup over your client"
    )
    mode.add_argument("--page", action="store_true", help="Show it in a pager, rendered by Rich")
    show_parser.set_defaults(func=cmd_show)

    brief_parser.set_defaults(func=lambda a: brief_parser.print_help())
