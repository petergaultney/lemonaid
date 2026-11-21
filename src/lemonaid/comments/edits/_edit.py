"""Applying a batch of edits, and what adding a comment returns."""

import typing as ty
from collections import abc

from .. import model


class Added(ty.NamedTuple):
    comment_id: str
    edits: list[model.Edit]


def apply(text: str, edits: abc.Iterable[model.Edit]) -> str:
    """Apply edits made against the same `text`; they must not overlap. Edits that
    insert at the same offset keep their order."""
    ordered = sorted(enumerate(edits), key=lambda ie: (ie[1].start, ie[1].end, ie[0]), reverse=True)
    for _, edit in ordered:
        text = text[: edit.start] + edit.text + text[edit.end :]
    return text
