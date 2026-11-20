"""Read a file into a `model.Document`.

Offsets are indexes into the file's text (`str`, not bytes), and every span is
half-open. A parse never fails: what it can't read becomes a `model.ParseError`, and
everything else is still returned. Markers inside Python strings and Markdown code are
text, not markers.
"""

from collections import abc

from . import kinds, lines, markers, model, records


def parse(text: str, kind: model.FileKind) -> model.Document:
    file_kind = kinds.get(kind)
    found_section, record_lines, section_errors = file_kind.find_section(text)
    comments, resolutions, record_errors = records.read(record_lines)
    body_end = found_section.start if found_section else len(text)
    body_scan = lines.masked(text[:body_end], file_kind.code_regions(text[:body_end]))
    found_markers = markers.find(text, body_scan, file_kind)
    anchors, anchor_errors = markers.pair(text, found_markers, body_end, file_kind)
    unclosed_string = file_kind.unclosed_string(text[:body_end])
    unclosed_errors = (
        [model.ParseError(unclosed_string, "a string starts here and is never closed", "string")]
        if unclosed_string is not None
        else []
    )

    return model.Document(
        kind=kind,
        markers=found_markers,
        anchors=anchors,
        comments=comments,
        resolutions=resolutions,
        errors=tuple(
            sorted(
                [
                    *section_errors,
                    *record_errors,
                    *anchor_errors,
                    *unclosed_errors,
                    *_link_errors(anchors, comments, resolutions),
                ]
            )
        ),
        section=found_section,
        newline=model.newline_of(text),
        unclosed_string=unclosed_string,
    )


def _link_error(offset: int, message: str) -> model.ParseError:
    return model.ParseError(offset, message, "link")


def _link_errors(
    anchors: tuple[model.Anchor, ...],
    comments: tuple[model.Comment, ...],
    resolutions: tuple[model.Resolution, ...],
) -> list[model.ParseError]:
    errors: list[model.ParseError] = []
    by_id: dict[str, model.Comment] = {}
    for comment in comments:
        if comment.id in by_id:
            errors.append(_link_error(comment.offset, f"comment id {comment.id} is used twice"))
        else:
            by_id[comment.id] = comment

    for comment in comments:
        parent = by_id.get(comment.re) if comment.re is not None else None
        if comment.re is not None and parent is None:
            errors.append(
                _link_error(
                    comment.offset,
                    f"comment {comment.id} answers {comment.re}, which doesn't exist",
                )
            )
        elif parent is not None and comment.span is not None and comment.span[1] > len(parent.body):
            errors.append(
                _link_error(
                    comment.offset,
                    f"comment {comment.id}'s span runs past the end of {parent.id}",
                )
            )

    errors += [
        _link_error(c.offset, f"comment {c.id} is not part of any thread")
        for c in by_id.values()
        if _comment_is_in_a_cycle(c, by_id)
    ]
    errors += [
        _link_error(r.offset, f"a resolution names {r.resolves}, which doesn't exist")
        for r in resolutions
        if r.resolves not in by_id
    ]
    errors += [
        _link_error(a.opening[0], f"anchor {a.id} has no comment")
        for a in anchors
        if a.id not in by_id
    ]
    errors += [
        _link_error(
            by_id[a.id].offset,
            f"anchor {a.id} belongs to a reply, not a thread's first comment",
        )
        for a in anchors
        if a.id in by_id and by_id[a.id].re is not None
    ]
    return errors


def _comment_is_in_a_cycle(comment: model.Comment, by_id: abc.Mapping[str, model.Comment]) -> bool:
    seen = {comment.id}
    current = comment
    while current.re is not None:
        parent = by_id.get(current.re)
        if parent is None:
            return False
        if parent.id in seen:
            return True
        seen.add(parent.id)
        current = parent
    return False
