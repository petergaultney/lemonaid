"""Move a thread's anchor to new text: its markers come out and new ones go in around the
range, as small edits so an editor keeps its cursor and marks. Only the editor offers it,
since markers are hidden there and moving them by hand is the only other way."""

from .. import kinds, model, parse
from . import _write
from ._edit import apply
from .strip import check_markers


def reanchor(
    text: str, kind: model.FileKind, comment_id: str, start: int, end: int
) -> list[model.Edit]:
    doc = _write.writable(text, kind)
    root = doc.comment(comment_id)
    if root is None or root.re is not None:
        raise ValueError(f"no thread {comment_id} in this file")
    body_end = doc.section.start if doc.section else len(text)
    if not 0 <= start <= end <= body_end:
        raise ValueError(f"range {start}-{end} is not in the file's body (0-{body_end})")

    carriers = sorted(m.carrier for m in check_markers(doc, {comment_id}))
    # a selection may cover the old markers, which are hidden in an editor, but neither end
    # may fall inside one
    if any(c_start < point < c_end for c_start, c_end in carriers for point in (start, end)):
        raise ValueError("an end of the new range is inside one of the thread's markers")
    removed = [model.Edit(c_start, c_end, "") for c_start, c_end in carriers]
    without = apply(text, removed)

    def to_without(offset: int) -> int:
        return offset - sum(c_end - c_start for c_start, c_end in carriers if c_end <= offset)

    def to_original(offset: int) -> int:
        for c_start, c_end in carriers:
            if c_start <= offset:
                offset += c_end - c_start
        return offset

    placed = kinds.get(kind).place_anchor(
        without, to_without(start), to_without(end), _write.writable(without, kind), comment_id
    )
    edits = removed + [model.Edit(to_original(e.start), to_original(e.end), e.text) for e in placed]
    moved = parse.parse(apply(text, edits), kind)
    if moved.anchor(comment_id) is None or len(moved.comments) != len(doc.comments):
        raise ValueError(
            "the file wouldn't read back as intended after this edit; nothing was written"
        )
    return edits
