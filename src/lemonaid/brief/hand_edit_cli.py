"""`lemonaid brief edit`: edit a lemon's brief in your editor, merged on quit with the lemon's own writes."""

import argparse
import subprocess
import sys
import textwrap
from pathlib import Path

from ..inbox import db
from ..log import get_logger
from . import hand_edit, lemon, store

_log = get_logger("brief.hand_edit")


def add_parser(brief_subparsers: argparse._SubParsersAction) -> None:
    summary = "Edit a lemon's brief in your editor, merged with what the lemon writes meanwhile"
    parser = brief_subparsers.add_parser("edit", help=summary, description=summary)
    parser.add_argument(
        "lemon", help="A Lemon-ID, an attached lemon's channel, or a brief's name or path"
    )
    parser.add_argument(
        "--editor",
        default="",
        help="The command to edit with (default: $VISUAL, then $EDITOR, then vi)",
    )
    parser.set_defaults(func=cmd_edit)


def _brief_path(target: str) -> tuple[Path | None, str]:
    if (given := Path(target).expanduser()).is_file():
        target = str(given.resolve())  # `lemon_id` reads a relative name inside the briefs folder
    try:
        with db.connect() as conn:
            path = lemon.brief_of(conn, lemon.lemon_id(conn, target))
    except (LookupError, ValueError, store.ChangedUnderneath) as error:
        return None, str(error)

    if path is None:
        return None, f"No brief found for {target!r}"

    if error := store.outside_error(path):
        return None, error

    return path, ""


def _edit_again(copy: Path, why: str) -> bool:
    """Whether the person wants to edit the copy again rather than stop with the brief unchanged."""
    print(
        textwrap.dedent(
            f"""
            {why}

              e  edit your copy again
              s  stop: the brief stays as it is now, and its lemon isn't told anything.
                 Your edited copy is kept at {copy}
            """
        ),
        file=sys.stderr,
    )
    try:
        return input("[e/s] ").strip().lower() == "e"
    except EOFError:
        return False


def _failed(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(1)


def cmd_edit(args: argparse.Namespace) -> None:
    path, error = _brief_path(args.lemon)
    if path is None:
        _failed(error)
        return

    editor = hand_edit.editor_command(args.editor)
    session = hand_edit.start(path)
    try:
        while True:
            exit_status = subprocess.run([*editor, str(session.copy)], check=False).returncode
            match hand_edit.after_editor(session, exit_status):
                case hand_edit.Finished(message):
                    print(message)
                    return
                case hand_edit.Choose(why) if _edit_again(session.copy, why):
                    continue
                case _:
                    _failed(hand_edit.stop(session))
                    return
    except (OSError, ValueError) as error:
        _log.warning("Editing %s failed: %s", path, error)
        _failed(f"{error}; your edit is in {session.copy}")
