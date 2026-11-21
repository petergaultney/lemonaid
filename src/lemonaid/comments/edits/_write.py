"""What every command that writes a record shares: ids, times, encoding, appending to
the threads section, and the checks before and after a write."""

import datetime as dt
import os
import re
import typing as ty
from collections import abc

import wordybin

from .. import kinds, model, parse, records
from ._edit import apply

_ID_ATTEMPTS: ty.Final = 50


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(doc: model.Document) -> str:
    """A WordyBin name no comment or anchor in `doc` uses."""
    taken = {c.id.lower() for c in doc.comments} | {m.id.lower() for m in doc.markers}
    for _ in range(_ID_ATTEMPTS):
        candidate = wordybin.encode(os.urandom(2))
        if candidate.lower() not in taken:
            return candidate
    raise ValueError(f"No free comment id after {_ID_ATTEMPTS} tries")


def encode(record: abc.Mapping[str, ty.Any], kind: model.FileKind, newline: str = "\n") -> str:
    """One record as its line in the threads section, line ending included."""
    return kinds.get(kind).encode_record(records.json_line(record), newline)


def append_record(text: str, doc: model.Document, record: abc.Mapping[str, ty.Any]) -> model.Edit:
    """Append `record` to the threads section, starting the section if there is none.

    A new section starts with a line ending, which `strip` removes with it.
    """
    newline = doc.newline
    line = encode(record, doc.kind, newline)
    if doc.section is not None:
        at = doc.section.insert_at
        needs_newline = at > 0 and text[at - 1] != "\n"
        return model.Edit(at, at, (newline if needs_newline else "") + line)
    return model.Edit(len(text), len(text), kinds.get(doc.kind).new_section(line, newline))


def writable(text: str, kind: model.FileKind) -> model.Document:
    if re.search(r"\r(?!\n)", text):
        raise ValueError("this file ends lines with a bare CR, which we don't write to")
    return parse.parse(text, kind)


def check_id_free(doc: model.Document, comment_id: str) -> None:
    taken = {c.id.lower() for c in doc.comments} | {m.id.lower() for m in doc.markers}
    if comment_id.lower() in taken:
        raise ValueError(f"id {comment_id} is already used in this file")


def check_readable(
    before: model.Document,
    text: str,
    edits: list[model.Edit],
    *,
    comment_id: str,
    new_markers: int,
) -> None:
    """Refuse edits whose result we can't read back as exactly what we meant to add: the
    new comment once, its anchor if it has one, and everything that was there before,
    with no new errors. The file's layout can defeat a write, as when an unclosed fence
    would swallow the threads section, and so can an insertion inside existing markup."""
    after = parse.parse(apply(text, edits), before.kind)
    new_comment_once = [c.id for c in after.comments].count(comment_id) == 1
    anchored_if_expected = new_markers == 0 or after.anchor(comment_id) is not None
    markers_kept = len(after.markers) == len(before.markers) + new_markers
    anchors_kept = {a.id for a in before.anchors} <= {a.id for a in after.anchors}
    no_new_errors = len(after.errors) == len(before.errors)
    if not (
        new_comment_once
        and anchored_if_expected
        and markers_kept
        and anchors_kept
        and no_new_errors
    ):
        raise ValueError(
            "the file wouldn't read back as intended after this edit; nothing was written"
        )
