"""Anchor a new thread and append its first comment."""

from .. import kinds, model
from . import _write
from ._edit import Added


def add_comment(
    text: str,
    kind: model.FileKind,
    start: int,
    end: int,
    *,
    author: str,
    body: str,
    at: str | None = None,
    comment_id: str | None = None,
) -> Added:
    """Anchor a new thread on `text[start:end]` and append its first comment.

    The file's kind places the markers (see `kinds`): a range that starts or ends inside
    code grows to cover it, since a marker there would be text. In Python an anchor
    covers whole lines, and an empty range anchors the line it is on; in Markdown an
    empty range is a point anchor.
    """
    doc = _write.writable(text, kind)
    body_end = doc.section.start if doc.section else len(text)
    if not 0 <= start <= end <= body_end:
        raise ValueError(f"range {start}-{end} is not in the file's body (0-{body_end})")
    start, end = _before_crlf(text, start), _before_crlf(text, end)

    if comment_id is not None:
        _write.check_id_free(doc, comment_id)
    comment_id = comment_id or _write.new_id(doc)
    anchor_edits = kinds.get(kind).place_anchor(text, start, end, doc, comment_id)
    record = {"id": comment_id, "author": author, "at": at or _write.now(), "body": body}
    added = Added(comment_id, [*anchor_edits, _write.append_record(text, doc, record)])
    _write.check_readable(
        doc, text, added.edits, comment_id=comment_id, new_markers=len(anchor_edits)
    )
    return added


def _before_crlf(text: str, position: int) -> int:
    """`position`, moved off the middle of a CRLF, where a marker would leave a bare CR."""
    between_cr_and_lf = 0 < position < len(text) and text[position - 1 : position + 1] == "\r\n"
    return position - 1 if between_cr_and_lf else position
