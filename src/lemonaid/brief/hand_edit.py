"""A person's edit of a brief, made in a copy and merged into the brief as it is by then.

The copy shows the brief as lemonaid's edit verbs see it: its frontmatter's fields as
header lines under the title (see `frontmatter.legacy`). The merge goes through
`verbs_cli.edit`, so it gets the same re-read before the write, the same atomic
replace and the same `brief check` refusal as any verb.
"""

import difflib
import typing as ty
from pathlib import Path

from . import frontmatter, three_way, verbs_cli

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
