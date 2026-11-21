"""What the server tells the editor about a document's comments: a diagnostic at each anchor
and format error, and the `lemonaid/threads` notification clients draw threads from.
"""

import dataclasses
import typing as ty
from collections import abc

from lsprotocol import types

from ..comments import model, threads
from . import positions

SOURCE: ty.Final = "lemonaid"
_GIST_LENGTH: ty.Final = 80


class ThreadsKey(ty.NamedTuple):
    """What decides whether clients need new threads: an anchor that only moved doesn't
    count, since clients track each anchor from where the last notification put it, and
    neither does a record that only moved because you typed above the section."""

    comments: tuple[model.Comment, ...]
    resolutions: tuple[model.Resolution, ...]
    anchor_ids: frozenset[str]


def threads_key(doc: model.Document) -> ThreadsKey:
    return ThreadsKey(
        comments=tuple(dataclasses.replace(c, offset=0) for c in doc.comments),
        resolutions=tuple(dataclasses.replace(r, offset=0) for r in doc.resolutions),
        anchor_ids=frozenset(a.id for a in doc.anchors),
    )


def threads_params(
    uri: str,
    version: int | None,
    text: str,
    doc: model.Document,
    codec: positions.Codec,
    unread: abc.Sequence[str] = (),
) -> dict[str, ty.Any]:
    """The `lemonaid/threads` parameters. Each thread's comments come in tree order, each
    with its `depth` below the root, so the tree needs no nesting (a long chain of replies
    would nest past what a JSON encoder will recurse through). `markers` are the thread's
    own markers, each the range of what removing it removes (its carrier) and that text,
    so a client can hide them without telling them from marker-shaped text itself, and
    can tell when its buffer no longer holds a marker where this notification put it."""
    return {
        "uri": uri,
        "version": version,
        "unread": list(unread),  # comments the person hasn't seen, from the file's inbox row
        "threads": [
            {
                "anchor": _range(codec, thread.anchor.start, thread.anchor.end)
                if thread.anchor
                else None,
                "markers": [
                    {"range": _range(codec, *carrier), "text": text[carrier[0] : carrier[1]]}
                    for carrier in (
                        (thread.anchor.opening, thread.anchor.closing) if thread.anchor else ()
                    )
                    if carrier is not None
                ],
                "comments": _comments_in_tree_order(thread.root),
            }
            for thread in threads.threads(doc)
        ],
    }


def diagnostics(doc: model.Document, codec: positions.Codec) -> list[types.Diagnostic]:
    hints = [
        types.Diagnostic(
            range=_lsp_range(codec, thread.anchor.start, thread.anchor.end),
            message=_hint(thread.root),
            severity=types.DiagnosticSeverity.Hint,
            source=SOURCE,
            code="comment",
        )
        for thread in threads.threads(doc)
        if thread.anchor is not None
    ]
    errors = [
        types.Diagnostic(
            range=_lsp_range(codec, error.offset, error.offset),
            message=error.message,
            severity=types.DiagnosticSeverity.Error,
            source=SOURCE,
            code=error.kind,
        )
        for error in doc.errors
    ]
    return [*hints, *errors]


def _hint(root: model.Node) -> str:
    first_line = root.comment.body.split("\n", 1)[0]
    gist = first_line if len(first_line) <= _GIST_LENGTH else first_line[: _GIST_LENGTH - 1] + "…"
    reply_count = _count(root) - 1
    replies = {0: "", 1: " (1 reply)"}.get(reply_count, f" ({reply_count} replies)")
    resolved = " [resolved]" if root.resolved else ""
    return f"{root.comment.author}: {gist}{replies}{resolved}"


def _count(root: model.Node) -> int:
    count, stack = 0, [root]
    while stack:
        node = stack.pop()
        count += 1
        stack += node.replies
    return count


def _comments_in_tree_order(root: model.Node) -> list[dict[str, ty.Any]]:
    shown = []
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        comment = node.comment
        shown.append(
            {
                "id": comment.id,
                "re": comment.re,
                "span": list(comment.span) if comment.span else None,
                "author": comment.author,
                "by": "lemon" if comment.by_lemon else "person",
                "at": comment.at,
                "body": comment.body,
                "resolved": node.resolved,
                "depth": depth,
            }
        )
        stack += [(reply, depth + 1) for reply in reversed(node.replies)]
    return shown


def _range(codec: positions.Codec, start: int, end: int) -> dict[str, dict[str, int]]:
    first, last = codec.position(start), codec.position(end)
    return {
        "start": {"line": first.line, "character": first.character},
        "end": {"line": last.line, "character": last.character},
    }


def _lsp_range(codec: positions.Codec, start: int, end: int) -> types.Range:
    first, last = codec.position(start), codec.position(end)
    return types.Range(
        start=types.Position(line=first.line, character=first.character),
        end=types.Position(line=last.line, character=last.character),
    )
