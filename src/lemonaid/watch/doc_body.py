"""Settling and attribution of a document's body changes."""

import difflib
import time
import typing as ty
from collections import abc

from . import body_norm, own_edits_replay

if ty.TYPE_CHECKING:
    from . import doc_events


def line_delta(old: str, new: str) -> str:
    added = removed = 0
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return f"+{added}/-{removed} lines"


def changed(
    w: "doc_events.DocWatch", body: str, settle: abc.Callable[[int], None]
) -> tuple[str, int]:
    own = (
        own_edits_replay.settles(w.own_root, w.writer, w.doc, w.consumed, w.settled_body, body)
        if w.writer
        else None
    )
    if own is not None:
        settle(own)
        return "", own

    if body_norm.normalized(body) == body_norm.normalized(w.settled_body):
        if body != w.settled_body:
            settle(w.consumed)
        w.pending_body = body
        return "", w.consumed

    if body_norm.normalized(body) != body_norm.normalized(w.pending_body):
        w.pending_body, w.pending_since = body, time.time()
        if w.quiet or not w.all_threads:
            return "", w.consumed

    if time.time() - w.pending_since < w.quiet:
        return "", w.consumed

    message = (
        f"{w.doc} was created ({line_delta(w.settled_body, body)}), quiet for {int(w.quiet or w.settled_quiet)}s"
        if not w.settled_body
        else f"body of {w.doc} changed ({line_delta(w.settled_body, body)}), quiet for {int(w.quiet or w.settled_quiet)}s"
    )
    return message, own_edits_replay.last_seq(w.own_root, w.writer, w.doc) if w.writer else 0
