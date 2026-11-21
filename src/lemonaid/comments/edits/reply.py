"""Append a reply to a comment."""

import typing as ty

from .. import model
from . import _write
from ._edit import Added


def reply(
    text: str,
    kind: model.FileKind,
    re_: str,
    *,
    author: str,
    body: str,
    span: tuple[int, int] | None = None,
    at: str | None = None,
    comment_id: str | None = None,
    by_lemon: bool = False,
) -> Added:
    """Append a reply to comment `re_`, about `span` of its body when given."""
    doc = _write.writable(text, kind)
    parent = doc.comment(re_)
    if parent is None:
        raise ValueError(f"no comment {re_} in this file")
    if span is not None and not 0 <= span[0] <= span[1] <= len(parent.body):
        raise ValueError(f"span {list(span)} is not in comment {re_}'s body")

    if comment_id is not None:
        _write.check_id_free(doc, comment_id)
    comment_id = comment_id or _write.new_id(doc)
    record: dict[str, ty.Any] = {"id": comment_id, "re": re_}
    if span is not None:
        record["span"] = list(span)
    record |= {"author": author, "at": at or _write.now(), "body": body}
    if by_lemon:
        record["by"] = "lemon"
    added = Added(comment_id, [_write.append_record(text, doc, record)])
    _write.check_readable(doc, text, added.edits, comment_id=comment_id, new_markers=0)
    return added
