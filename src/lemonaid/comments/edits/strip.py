"""Remove every marker and the threads section from a file."""

from .. import model, parse
from ._edit import apply


def strip(text: str, kind: model.FileKind) -> str:
    """`text` without markers or the threads section; see `strip_edits`."""
    return apply(text, strip_edits(text, kind))


def strip_edits(text: str, kind: model.FileKind) -> list[model.Edit]:
    """The edits that remove the markers and the threads section, small ones, so an editor
    applying them keeps its cursor and marks.

    A marker is ours to remove when the file has a thread whose first comment has its id,
    even if its pair is missing; each removes what its spelling says (see `docs/comments.md`). Any other
    marker-shaped text, such as an example in code our masking misread, stays. Text
    after a Markdown threads section stays too. We refuse an id with two opening or two
    closing markers, or a closing marker before its opening one, since one of them may be
    an example.
    We refuse a file with a string that is never closed, a Markdown section with no
    closing `-->`, or a section with a line we can't read, because in each case we
    can't be sure what is ours to remove.
    """
    doc = parse.parse(text, kind)
    if doc.unclosed_string is not None:
        raise ValueError("a string in this file is never closed; close it before stripping")
    if doc.section is not None and not doc.section.closed:
        raise ValueError("the threads section has no closing -->; close it before stripping")
    if doc.section is not None and any(
        doc.section.start <= e.offset < doc.section.end and e.kind == "record" for e in doc.errors
    ):
        raise ValueError("the threads section has a line that isn't a record; fix it first")

    our_ids = {c.id for c in doc.comments if c.re is None}
    our_markers = check_markers(doc, our_ids)

    edits = [model.Edit(*marker.carrier, "") for marker in our_markers]
    if doc.section is not None:
        edits.append(model.Edit(blank_lines_before(text, doc.section.start), doc.section.end, ""))
    return edits


def blank_lines_before(text: str, start: int) -> int:
    """Where the empty lines just above the section begin, keeping the body's own last line
    ending. We write one empty line there; a formatter may add more (ruff wants two before
    a top-level comment after a function), and they are ours to remove with the section."""
    while True:
        for ending in ("\r\n", "\n", "\r"):
            if text.endswith(ending + ending, 0, start):
                start -= len(ending)
                break
        else:
            return start


def check_markers(doc: model.Document, ids: set[str]) -> list[model.Marker]:
    """The markers of the threads `ids`, which a command may remove. We refuse an id with two
    opening or two closing markers, or a closing marker before its opening one, since one
    of them may be an example and we can't tell which is the thread's."""
    markers = [m for m in doc.markers if m.id in ids]
    seen: set[tuple[str, bool]] = set()
    for marker in markers:
        if (marker.id, marker.closing) in seen:
            raise ValueError(
                f"anchor {marker.id} has more than one {'closing' if marker.closing else 'opening'}"
                " marker, and one may be an example; remove the extra one first"
            )
        seen.add((marker.id, marker.closing))
    openings = {m.id: m.carrier[0] for m in markers if not m.closing}
    for marker in markers:
        if marker.closing and marker.id in openings and marker.carrier[0] < openings[marker.id]:
            raise ValueError(
                f"anchor {marker.id} closes before it opens, and one marker may be an example;"
                " remove the extra one first"
            )
    return markers
