"""CLI for showing where a lemon's work stands, from its brief."""

import argparse
import dataclasses
import sys
import time
from pathlib import Path

from ..inbox import db
from . import attached, popup, session, status, target, write_cli


def _target(
    session_arg: str,
    file_args: list[str],
    dir_args: list[str],
    place_arg: str,
    name_args: list[str],
) -> target.Target:
    if file_args or dir_args:
        return target.Target(
            [Path(f) for f in file_args],
            [Path(d) for d in dir_args],
            Path(place_arg) if place_arg else None,
            name_args,
            Path((file_args or dir_args)[0]).name,
        )

    tmux_session, _, window = (session_arg or session.current_session()).partition(":")
    if not tmux_session:
        print("Not in tmux; name a session or pass --dir.", file=sys.stderr)
        sys.exit(1)

    with db.connect() as conn:
        rows = db.get_active(conn)
        found = target.for_session(tmux_session, rows, attached.for_rows(conn, rows), window)

    if not (found.attached or found.dirs):
        print(f"No tmux session or inbox row for '{tmux_session}'.", file=sys.stderr)
        sys.exit(1)

    return dataclasses.replace(found, names=[*found.names, *name_args])


def cmd_show(args: argparse.Namespace) -> None:
    found = _target(args.session, args.file, args.dir, args.place, args.name)
    if args.popup:
        popup.open_popup(found)
        return

    markdown = status.render(found.attached, found.dirs, found.place, found.names, time.time())
    if args.page:
        popup.page(markdown, args.dismiss)
    else:
        print(markdown)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    brief_parser = subparsers.add_parser(
        "brief",
        help="Where a lemon's work stands, from its brief",
        description="A brief is a Markdown file in ~/.brief-lemons/ attached to one "
        "lemon session (or, for older sessions, .z/brief.md or .z/brief-<name>.md in its "
        "place). Its Status line and `## Now` section are what the worker keeps current.",
    )
    brief_subparsers = brief_parser.add_subparsers(dest="brief_command")

    show_parser = brief_subparsers.add_parser(
        "show",
        help="Print a session's Status and Now, or show them in a popup",
        description="Shows the briefs attached to the session's lemons. A session with "
        "none falls back to .z/: it looks in the directories of the session's lemons "
        "(from the inbox), then the session's own directory (from tmux), and shows the "
        "first brief found, "
        "never looking above the session's directory: "
        "the one named for the lemon's LEMON_NAME, backend, or session if there is one, "
        "otherwise every brief there, newest first. Falls back to .z/state.md when "
        "there is no brief.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    show_parser.add_argument(
        "session",
        nargs="?",
        default="",
        metavar="SESSION[:WINDOW]",
        help="tmux session, and the window of one lemon in it (default: the calling pane's)",
    )
    show_parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Show this brief instead of asking the inbox and tmux (repeatable)",
    )
    show_parser.add_argument(
        "--dir",
        action="append",
        default=[],
        help="Read this directory instead of asking the inbox and tmux (repeatable, in order)",
    )
    show_parser.add_argument(
        "--place",
        default="",
        help="With --dir, also look in .z/ above a --dir, up to and including this "
        "directory (without it, only each --dir's own .z/ is read)",
    )
    show_parser.add_argument(
        "--name",
        action="append",
        default=[],
        help="Also prefer .z/brief-NAME.md (repeatable)",
    )
    show_parser.add_argument(
        "--dismiss",
        action="append",
        default=[],
        help="With --page, also quit on this lesskey key sequence (repeatable)",
    )
    mode = show_parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--popup", action="store_true", help="Show it in a tmux popup over your client"
    )
    mode.add_argument("--page", action="store_true", help="Show it in a pager, rendered by Rich")
    show_parser.set_defaults(func=cmd_show)

    write_cli.add_parsers(brief_subparsers)

    brief_parser.set_defaults(func=lambda a: brief_parser.print_help())
