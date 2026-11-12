"""A line-based three-way merge, as `diff3 -m` does it.

*base* is the text both sides started from. A stretch of lines only one side changed
takes that side's lines; a stretch both changed the same way takes them once; a stretch
both changed differently is a conflict, written between markers with *ours* first.
"""

import difflib
import typing as ty
from collections import abc

OURS_MARKER = "<<<<<<<"
SEPARATOR = "======="
THEIRS_MARKER = ">>>>>>>"


class Merged(ty.NamedTuple):
    text: str
    conflicts: int


class _Sync(ty.NamedTuple):
    """Lines all three texts share: base[base_start:base_end] and the same in each side."""

    base_start: int
    base_end: int
    ours_start: int
    theirs_start: int


def _yield_syncs(
    base: abc.Sequence[str], ours: abc.Sequence[str], theirs: abc.Sequence[str]
) -> ty.Iterator[_Sync]:
    """The stretches of *base* that neither side changed, in order, ending with an empty one at the end."""
    ours_blocks = difflib.SequenceMatcher(None, base, ours, autojunk=False).get_matching_blocks()
    theirs_blocks = difflib.SequenceMatcher(
        None, base, theirs, autojunk=False
    ).get_matching_blocks()
    i_ours = i_theirs = 0
    while i_ours < len(ours_blocks) and i_theirs < len(theirs_blocks):
        o_base, o_side, o_len = ours_blocks[i_ours]
        t_base, t_side, t_len = theirs_blocks[i_theirs]
        start, end = max(o_base, t_base), min(o_base + o_len, t_base + t_len)
        if start < end:
            yield _Sync(start, end, o_side + start - o_base, t_side + start - t_base)

        if o_base + o_len < t_base + t_len:
            i_ours += 1
        else:
            i_theirs += 1

    yield _Sync(len(base), len(base), len(ours), len(theirs))


def merge(base: str, ours: str, theirs: str, ours_label: str, theirs_label: str) -> Merged:
    base_lines = base.splitlines(keepends=True)
    ours_lines = ours.splitlines(keepends=True)
    theirs_lines = theirs.splitlines(keepends=True)

    out: list[str] = []
    conflicts = 0
    base_at = ours_at = theirs_at = 0
    for sync in _yield_syncs(base_lines, ours_lines, theirs_lines):
        base_chunk = base_lines[base_at : sync.base_start]
        ours_chunk = ours_lines[ours_at : sync.ours_start]
        theirs_chunk = theirs_lines[theirs_at : sync.theirs_start]
        if ours_chunk in (base_chunk, theirs_chunk):
            out.extend(theirs_chunk)
        elif theirs_chunk == base_chunk:
            out.extend(ours_chunk)
        else:
            conflicts += 1
            out.extend(
                [
                    f"{OURS_MARKER} {ours_label}\n",
                    *_terminated(ours_chunk),
                    f"{SEPARATOR}\n",
                    *_terminated(theirs_chunk),
                    f"{THEIRS_MARKER} {theirs_label}\n",
                ]
            )

        length = sync.base_end - sync.base_start
        out.extend(base_lines[sync.base_start : sync.base_end])
        base_at = sync.base_end
        ours_at = sync.ours_start + length
        theirs_at = sync.theirs_start + length

    return Merged("".join(out), conflicts)


def _terminated(lines: list[str]) -> list[str]:
    """*lines* with a newline on the last, so a marker after it starts its own line."""
    return (
        [*lines[:-1], lines[-1] if lines[-1].endswith("\n") else lines[-1] + "\n"] if lines else []
    )


def marker_count(text: str, ours_label: str, theirs_label: str) -> int:
    """How many lines of *text* are the markers `merge` writes with these labels.

    A brief can hold marker lines of its own, such as an example in a code fence, so a
    caller compares this count with the text's before the merge rather than with zero.
    """
    markers = {f"{OURS_MARKER} {ours_label}", f"{THEIRS_MARKER} {theirs_label}"}
    return sum(line.rstrip() in markers for line in text.splitlines())
