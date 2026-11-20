"""The changes a lemon asks for, as data, so `lemonaid comments` can apply one to the file or
send it to the editor server that has the file open, and both compute the same edits.
"""

import typing as ty

from . import edits, listing, model, parse


class Add(ty.NamedTuple):
    lines: str  # `<a>-<b>` or `<a>`, 1-based and inclusive
    author: str
    body: str


class Reply(ty.NamedTuple):
    re: str
    author: str
    body: str


class Resolve(ty.NamedTuple):
    id: str
    author: str


class Strip(ty.NamedTuple):
    pass


Operation = Add | Reply | Resolve | Strip


def edits_for(
    operation: Operation,
    text: str,
    kind: model.FileKind,
    *,
    at: str | None = None,
    comment_id: str | None = None,
) -> tuple[list[model.Edit], str | None]:
    """The edits against `text` that carry out `operation`, and the new comment's id when it
    writes one. `at` and `comment_id` fix the record's time and id, so the same operation
    tried again writes the same record. Raises ValueError for what the model refuses."""
    match operation:
        case Add(lines, author, body):
            start, end = line_range(text, lines)
            added = edits.add_comment(
                text, kind, start, end, author=author, body=body, at=at, comment_id=comment_id
            )
            return added.edits, added.comment_id
        case Reply(re_, author, body):
            added = edits.reply(
                text, kind, re_, author=author, body=body, at=at, comment_id=comment_id
            )
            return added.edits, added.comment_id
        case Resolve(resolved_id, author):
            return [edits.resolve(text, kind, resolved_id, author=author, at=at)], None
        case Strip():
            stripped = edits.strip(text, kind)
            return ([model.Edit(0, len(text), stripped)] if stripped != text else []), None


def landed(
    operation: Operation, text: str, kind: model.FileKind, *, at: str, comment_id: str | None
) -> bool:
    """Whether `text` already holds what `edits_for(operation, ..., at=at)` wrote, the
    comment `comment_id` for one that writes a comment."""
    match operation:
        case Add() | Reply():
            return (
                comment_id is not None and parse.parse(text, kind).comment(comment_id) is not None
            )
        case Resolve(resolved_id, author):
            return any(
                r.resolves == resolved_id and r.author == author and r.at == at
                for r in parse.parse(text, kind).resolutions
            )
        case Strip():
            return edits.strip(text, kind) == text


def line_range(text: str, lines: str) -> tuple[int, int]:
    """`a-b` or `a` (1-based, inclusive) as offsets from the start of line a to the end of
    line b's text, before its own line ending. The empty "line" after a file's last line
    ending is not a line."""
    first_text, _, last_text = lines.partition("-")
    try:
        first, last = int(first_text), int(last_text or first_text)
    except ValueError:
        raise ValueError(f"--lines {lines}: expected <a>-<b> or <a>") from None
    starts = listing.line_starts(text)
    line_count = len(starts) - (starts[-1] == len(text))
    if not 1 <= first <= last <= line_count:
        raise ValueError(f"--lines {lines}: the file has {line_count} line(s)")
    last_line_end = starts[last] if last < len(starts) else len(text)
    last_line_text = text[starts[last - 1] : last_line_end].rstrip("\r\n")
    return starts[first - 1], starts[last - 1] + len(last_line_text)


def to_json(operation: Operation) -> dict[str, ty.Any]:
    return {"op": type(operation).__name__.lower(), **operation._asdict()}


def from_json(data: dict[str, ty.Any]) -> Operation:
    """Raises ValueError for anything but what `to_json` writes."""
    fields = {k: v for k, v in data.items() if k != "op"}
    if not all(isinstance(v, str) for v in fields.values()):
        raise ValueError("every field of an operation is a string")
    try:
        match data.get("op"):
            case "add":
                return Add(**fields)
            case "reply":
                return Reply(**fields)
            case "resolve":
                return Resolve(**fields)
            case "strip":
                return Strip(**fields)
    except TypeError:
        pass
    raise ValueError(f"not an operation: {data!r}")
