"""A person's edit of a brief, made in a copy and merged into the brief as it is by then.

The copy shows the brief as lemonaid's edit verbs see it: its frontmatter's fields as
header lines under the title (see `frontmatter.legacy`). The merge goes through
`verbs_cli.edit`, so it gets the same re-read before the write, the same atomic
replace and the same `brief check` refusal as any verb.

A `Session` is one edit from start to finish. Whoever runs the editor (the CLI in its
terminal, `lma` in a popup or in place) hands each exit to `after_editor`, which either
finishes or says why the person must choose to edit the copy again or stop.
"""

import dataclasses
import difflib
import os
import shlex
import shutil
import tempfile
import typing as ty
from pathlib import Path

from ..log import get_logger
from ..messages import to_brief
from . import frontmatter, three_way, verbs_cli

_log = get_logger("brief.hand_edit")

YOURS = "your edit"
THEIRS = "the brief now"


class Applied(ty.NamedTuple):
    diff: str  # what the merge changed in the brief, "" when the brief already said it


class Conflicted(ty.NamedTuple):
    text: str  # the copy to edit again, with the conflicting lines between markers
    theirs: str  # the brief it was merged against: the base for the next try


class _Conflict(Exception):
    def __init__(self, conflicted: Conflicted) -> None:
        super().__init__("conflict")
        self.conflicted = conflicted


def copy_text(path: Path) -> str:
    return frontmatter.legacy(path.read_text())


def apply(path: Path, base: str, yours: str) -> Applied | Conflicted | str:
    """Merge the change from *base* to *yours* into the brief at *path*; a string is why it was refused."""
    diffs: list[str] = []

    def merged(current: str) -> str:
        result = three_way.merge(base, yours, current, YOURS, THEIRS)
        if result.conflicts:
            raise _Conflict(Conflicted(result.text, current))

        return result.text

    def written(before: str, after: str) -> None:
        diffs.append(_diff(before, after))  # of the file itself, so its line numbers are the file's

    try:
        error = verbs_cli.edit(path, merged, written=written)
    except _Conflict as conflict:
        return conflict.conflicted

    return error or Applied(diffs[0] if diffs else "")


def _diff(before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            "before",
            "after",
        )
    )


def message(diff: str) -> str:
    """What the brief's lemon is told, so its next write starts from the brief as it is now."""
    return f"I edited your brief by hand. Read it again before you next change it. This is what changed:\n\n```diff\n{diff}```\n"


def editor_command(explicit: str = "") -> list[str]:
    """*explicit*, else $VISUAL, then $EDITOR, then vi, split as a shell would."""
    return shlex.split(explicit or os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi")


@dataclasses.dataclass
class Session:
    path: Path  # the brief
    copy: Path  # what the person edits, alone in a folder of its own
    base: str  # the brief as the copy last started from it
    conflicted: bool = False  # whether conflict markers were written into the copy


class Finished(ty.NamedTuple):
    message: str  # what happened; the copy is gone


class Choose(ty.NamedTuple):
    why: str  # why the person must edit the copy again (`resume`) or stop (`stop`)


def start(path: Path) -> Session:
    copy = Path(tempfile.mkdtemp(prefix="lemonaid-brief-edit-")) / path.name
    text = copy_text(path)
    copy.write_text(text)
    return Session(path, copy, text)


def after_editor(session: Session, exit_status: int) -> Finished | Choose:
    """Act on the copy after the editor exited with *exit_status*."""
    if exit_status != 0:  # such as Vim's `:cq`: whatever was saved isn't meant to be applied
        return Choose(f"The editor exited with status {exit_status}, so nothing was applied.")

    yours = session.copy.read_text()
    if session.conflicted and _markers(yours) > _markers(session.base):
        return Choose("Your copy still has conflict markers.")

    if yours == session.base:
        return _finished(session, "No change")

    outcome = apply(session.path, session.base, yours)
    if isinstance(outcome, Conflicted):
        session.copy.write_text(outcome.text)
        session.base = outcome.theirs
        session.conflicted = True
        return Choose(
            "The brief changed meanwhile in lines you edited. Your copy now shows both, between"
            f" `{three_way.OURS_MARKER} {YOURS}` and `{three_way.THEIRS_MARKER} {THEIRS}`."
        )

    if isinstance(outcome, str):
        return Choose(outcome)

    if not outcome.diff:
        return _finished(session, "The brief already says what your edit says")

    try:
        to_brief.send(session.path, message(outcome.diff))
    except (OSError, ValueError) as error:
        _log.warning("Saved %s but could not tell its lemon: %s", session.path, error)
        return _finished(
            session, f"Saved {session.path.name}, but couldn't tell its lemon: {error}"
        )

    return _finished(session, f"Saved {session.path.name}, and told its lemon what changed")


def stop(session: Session) -> str:
    """Leave the brief as it is and keep the copy; what to tell the person."""
    return f"Stopped: the brief is unchanged. Your edit is in {session.copy}"


def _finished(session: Session, said: str) -> Finished:
    shutil.rmtree(session.copy.parent, ignore_errors=True)
    return Finished(said)


def _markers(text: str) -> int:
    return three_way.marker_count(text, YOURS, THEIRS)
