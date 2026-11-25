"""Delete a comment, every reply below it and their resolutions; for a thread's first comment,
its markers too. The one edit besides `strip` that removes records, and only the editor
offers it: a person tidies a thread with it, and a lemon has no way to delete a comment.
"""

from .. import model, parse
from . import _write
from ._edit import apply
from .strip import check_markers, strip_edits


def delete(text: str, kind: model.FileKind, comment_id: str) -> list[model.Edit]:
    doc = _write.writable(text, kind)
    target = doc.comment(comment_id)
    if target is None:
        raise ValueError(f"no comment {comment_id} in this file")

    doomed = _with_replies(doc, comment_id)
    if len(doomed) == len(doc.comments):
        # the last comment: everything goes as `strip` removes it, with its checks, so a
        # section with a line we can't read is refused rather than removed
        return strip_edits(text, kind)

    records = [c.offset for c in doc.comments if c.id in doomed]
    records += [r.offset for r in doc.resolutions if r.resolves in doomed]
    edits = [model.Edit(offset, _line_end(text, offset), "") for offset in records]
    if target.re is None:
        edits += [model.Edit(*m.carrier, "") for m in check_markers(doc, {comment_id})]
    after = apply(text, edits)
    if len(parse.parse(after, kind).comments) != len(doc.comments) - len(doomed):
        raise ValueError(
            "the file wouldn't read back as intended after this edit; nothing was written"
        )
    return edits


def _with_replies(doc: model.Document, comment_id: str) -> set[str]:
    doomed, frontier = {comment_id}, [comment_id]
    while frontier:
        parent = frontier.pop()
        for comment in doc.comments:
            if comment.re == parent and comment.id not in doomed:
                doomed.add(comment.id)
                frontier.append(comment.id)
    return doomed


def _line_end(text: str, offset: int) -> int:
    end = text.find("\n", offset)
    return len(text) if end < 0 else end + 1
