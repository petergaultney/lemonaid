"""Append a resolution, which closes a comment and every reply below it."""

from .. import model, parse
from . import _write
from ._edit import apply


def resolve(
    text: str, kind: model.FileKind, comment_id: str, *, author: str, at: str | None = None
) -> model.Edit:
    doc = _write.writable(text, kind)
    if doc.comment(comment_id) is None:
        raise ValueError(f"no comment {comment_id} in this file")
    edit = _write.append_record(
        text, doc, {"resolves": comment_id, "author": author, "at": at or _write.now()}
    )
    after = parse.parse(apply(text, [edit]), kind)
    if len(after.resolutions) != len(doc.resolutions) + 1 or len(after.errors) != len(doc.errors):
        raise ValueError(
            "the file wouldn't read back as intended after this edit; nothing was written"
        )
    return edit
