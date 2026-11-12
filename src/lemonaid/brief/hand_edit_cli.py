"""`lemonaid brief edit`: edit a lemon's brief in your editor, merged on quit with the lemon's own writes."""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from ..inbox import db
from ..log import get_logger
from ..messages import to_brief
from . import hand_edit, lemon, store, three_way

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
    parser.add_argument(
        "--popup",
        action="store_true",
        help="Wait for Enter after a failure, so a popup doesn't close before it can be read",
    )
    parser.set_defaults(func=cmd_edit)


def editor() -> str:
    return os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"


def command(path: Path, editor_command: str, *, popup: bool = False) -> list[str]:
    """The command `lma` runs: this same lemonaid, with the editor of the person running `lma`."""
    return [
        sys.executable,
        "-m",
        "lemonaid.cli",
        "brief",
        "edit",
        str(path),
        "--editor",
        editor_command,
        *(["--popup"] if popup else []),
    ]


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


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return ""


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
    return _ask("[e/s] ") == "e"


def _failed(args: argparse.Namespace, message: str) -> None:
    print(message, file=sys.stderr)
    if args.popup:
        _ask("Press Enter to close ")
    sys.exit(1)


def _markers(text: str) -> int:
    return three_way.marker_count(text, hand_edit.YOURS, hand_edit.THEIRS)


class _Kept(Exception):
    def __init__(self, copy: Path) -> None:
        super().__init__(f"Stopped: the brief is unchanged. Your edit is in {copy}")


def _edit_until_applied(path: Path, copy: Path, editor_command: list[str]) -> str:
    """Edit *copy* and merge it into *path* until it applies, returning what happened.

    Raises `_Kept` when the person stops before it applies, leaving their edit in *copy*.
    """
    base = copy.read_text()
    conflicted = False
    while True:
        exit_status = subprocess.run([*editor_command, str(copy)], check=False).returncode
        if exit_status != 0:  # such as Vim's `:cq`: whatever was saved isn't meant to be applied
            if _edit_again(
                copy, f"The editor exited with status {exit_status}, so nothing was applied."
            ):
                continue
            raise _Kept(copy)

        yours = copy.read_text()
        if conflicted and _markers(yours) > _markers(base):
            if _edit_again(copy, "Your copy still has conflict markers."):
                continue
            raise _Kept(copy)

        if yours == base:
            return "No change"

        outcome = hand_edit.apply(path, base, yours)
        if isinstance(outcome, hand_edit.Conflicted):
            copy.write_text(outcome.text)
            base = outcome.theirs
            conflicted = True
            if _edit_again(
                copy,
                f"The brief changed meanwhile in lines you edited. Your copy now shows both, between"
                f" `{three_way.OURS_MARKER} {hand_edit.YOURS}` and"
                f" `{three_way.THEIRS_MARKER} {hand_edit.THEIRS}`.",
            ):
                continue
            raise _Kept(copy)

        if isinstance(outcome, str):
            if _edit_again(copy, outcome):
                continue
            raise _Kept(copy)

        if not outcome.diff:
            return "The brief already says what your edit says"

        try:
            to_brief.send(path, hand_edit.message(outcome.diff))
        except (OSError, ValueError) as error:
            _log.warning("Saved %s but could not tell its lemon: %s", path, error)
            return f"Saved {path.name}, but couldn't tell its lemon: {error}"

        return f"Saved {path.name}, and told its lemon what changed"


def cmd_edit(args: argparse.Namespace) -> None:
    path, error = _brief_path(args.lemon)
    if path is None:
        _failed(args, error)
        return

    editor_command = shlex.split(args.editor or editor())
    folder = Path(tempfile.mkdtemp(prefix="lemonaid-brief-edit-"))
    copy = folder / path.name
    copy.write_text(hand_edit.copy_text(path))
    try:
        outcome = _edit_until_applied(path, copy, editor_command)
    except _Kept as kept:
        _failed(args, str(kept))
        return
    except (OSError, ValueError) as error:
        _log.warning("Editing %s failed: %s", path, error)
        _failed(args, f"{error}; your edit is in {copy}")
        return

    shutil.rmtree(folder, ignore_errors=True)
    print(outcome)
