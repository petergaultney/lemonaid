"""Settling and attribution of a document's body changes."""

import time
import typing as ty
from collections import abc

from . import body_norm, doc_diff, own_edits_replay

if ty.TYPE_CHECKING:
    from . import doc_events


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

    summary, hunks = doc_diff.describe(w.settled_body, body)
    message = (
        f"{w.doc} was created ({summary}), quiet for {int(w.quiet or w.settled_quiet)}s"
        if not w.settled_body
        else f"body of {w.doc} changed ({summary}), quiet for {int(w.quiet or w.settled_quiet)}s"
    )
    if hunks:
        message += "\n" + hunks
    return message, own_edits_replay.last_seq(w.own_root, w.writer, w.doc) if w.writer else 0
