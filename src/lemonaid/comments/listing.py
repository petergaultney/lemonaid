"""Threads as readable text, for a lemon reading a file's comments in a terminal."""

import bisect
import re
import typing as ty
from collections import abc

from . import model, threads

_LINE_END: ty.Final = re.compile(r"\r\n|\r|\n")
_EXCERPT_LINES: ty.Final = 12


def line_starts(text: str) -> list[int]:
    """The offset where each line starts; line n (1-based) starts at `line_starts(text)[n - 1]`."""
    return [0, *(m.end() for m in _LINE_END.finditer(text))]


def anchor_lines(starts: abc.Sequence[int], anchor: model.Anchor) -> tuple[int, int]:
    """The first and last line (1-based) the anchored text is on."""
    first = bisect.bisect_right(starts, anchor.start)
    ends_at_a_line_start = anchor.end > anchor.start and anchor.end in starts
    last = bisect.bisect_right(starts, anchor.end - ends_at_a_line_start)
    return first, max(first, last)


def render(
    text: str,
    doc: model.Document,
    *,
    unanswered_for: abc.Set[str] | None = None,
    with_resolved: bool = False,
) -> str:
    """Every thread with its anchored lines and its replies as an indented tree.

    With `unanswered_for`, only threads holding a comment unanswered for those names, with
    those comments marked. Resolved branches are left out unless `with_resolved`.
    """
    unanswered_ids = (
        {c.id for c in threads.unanswered(doc, unanswered_for)}
        if unanswered_for is not None
        else set()
    )
    starts = line_starts(text)
    blocks = [
        _thread_text(text, starts, thread, unanswered_ids, with_resolved)
        for thread in threads.threads(doc)
        if (unanswered_for is None or _holds(thread.root, unanswered_ids))
        and (with_resolved or not thread.root.resolved)
    ]
    return "\n\n".join(blocks)


def errors_text(text: str, doc: model.Document) -> list[str]:
    starts = line_starts(text)
    return [f"line {bisect.bisect_right(starts, e.offset)}: {e.message}" for e in doc.errors]


def _holds(node: model.Node, ids: abc.Set[str]) -> bool:
    stack = [node]
    while stack:
        current = stack.pop()
        if current.comment.id in ids:
            return True
        stack += current.replies
    return False


def _thread_text(
    text: str,
    starts: abc.Sequence[int],
    thread: model.Thread,
    unanswered_ids: abc.Set[str],
    with_resolved: bool,
) -> str:
    return "\n".join(
        [
            *_anchor_text(text, starts, thread),
            *_tree_text(thread.root, unanswered_ids, with_resolved),
        ]
    )


def _anchor_text(text: str, starts: abc.Sequence[int], thread: model.Thread) -> list[str]:
    root_id = thread.root.comment.id
    if thread.anchor is None:
        return [f"{root_id}: orphaned, its anchor is gone"]

    first, last = anchor_lines(starts, thread.anchor)
    where = f"line {first}" if first == last else f"lines {first}-{last}"
    shown = range(first, min(last, first + _EXCERPT_LINES - 1) + 1)
    width = len(str(shown[-1]))
    excerpt = [f"  {n:>{width}} | {_line(text, starts, n)}" for n in shown]
    more = last - shown[-1]
    return [
        f"{root_id}: {where}",
        *excerpt,
        *([f"  ... {more} more line(s)"] if more else []),
    ]


def _line(text: str, starts: abc.Sequence[int], number: int) -> str:
    start = starts[number - 1]
    end = starts[number] if number < len(starts) else len(text)
    return _LINE_END.sub("", text[start:end])


def _tree_text(root: model.Node, unanswered_ids: abc.Set[str], with_resolved: bool) -> list[str]:
    out: list[str] = []
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if node.resolved and not with_resolved:
            continue
        out += _comment_text(node, depth, node.comment.id in unanswered_ids)
        stack += [(reply, depth + 1) for reply in reversed(node.replies)]
    return out


def _comment_text(node: model.Node, depth: int, unanswered: bool) -> list[str]:
    comment = node.comment
    marks = [
        *([f"re {comment.re}"] if comment.re else []),
        *([f"about chars {comment.span[0]}-{comment.span[1]}"] if comment.span else []),
        comment.at,
        *(["resolved"] if node.resolved else []),
        *(["UNANSWERED"] if unanswered else []),
    ]
    indent = "    " * depth
    body_lines = comment.body.splitlines() or [""]
    return [
        f"{indent}- [{comment.id}] {comment.author} ({', '.join(marks)})",
        *(f"{indent}  {line}" for line in body_lines),
    ]
