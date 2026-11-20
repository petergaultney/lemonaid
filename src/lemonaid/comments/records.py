"""The records in a threads section: reading and validating them, and writing one."""

import json
import re
import typing as ty
from collections import abc

from . import model

_LINE_SEPARATORS: ty.Final = {"\u2028": "\\u2028", "\u2029": "\\u2029"}


class RecordLine(ty.NamedTuple):
    offset: int
    json_text: str


def _record_error(offset: int, message: str) -> model.ParseError:
    return model.ParseError(offset, message, "record")


def json_line(record: abc.Mapping[str, ty.Any]) -> str:
    """One record as JSON on one line. We escape U+2028 and U+2029, which some readers
    take for line breaks; each kind wraps the line for its file."""
    line = json.dumps(record, ensure_ascii=False)
    for separator, escaped in _LINE_SEPARATORS.items():
        line = line.replace(separator, escaped)
    return line


def read(
    lines: abc.Iterable[RecordLine],
) -> tuple[tuple[model.Comment, ...], tuple[model.Resolution, ...], list[model.ParseError]]:
    comments: list[model.Comment] = []
    resolutions: list[model.Resolution] = []
    errors: list[model.ParseError] = []

    for line in lines:
        try:
            obj = json.loads(line.json_text)
        except json.JSONDecodeError as e:
            errors.append(_record_error(line.offset, f"a record is not JSON: {e.msg}"))
            continue
        except (ValueError, RecursionError):
            # The decoder's own limits: an integer too long to convert, nesting too deep.
            errors.append(_record_error(line.offset, "a record is too large to read"))
            continue

        record = _record(obj, line.offset)
        if isinstance(record, model.ParseError):
            errors.append(record)
        elif isinstance(record, model.Comment):
            comments.append(record)
        else:
            resolutions.append(record)

    return tuple(comments), tuple(resolutions), errors


_COMMENT_FIELDS: ty.Final = frozenset({"id", "author", "at", "body", "re", "span"})


_RESOLUTION_FIELDS: ty.Final = frozenset({"resolves", "author", "at"})


_SURROGATE: ty.Final = re.compile("[\ud800-\udfff]")


def _is_unicode(obj: dict[str, ty.Any]) -> bool:
    """Whether every string in the record, keys included, can be written as UTF-8: JSON's
    `\\ud800` escape decodes to a lone surrogate, which can't. Walked with a stack, since a
    record may nest deeper than the recursion limit allows."""
    stack: list[object] = [obj]
    while stack:
        value = stack.pop()
        if isinstance(value, str):
            if _SURROGATE.search(value):
                return False
        elif isinstance(value, dict):
            stack += value.keys()
            stack += value.values()
        elif isinstance(value, list):
            stack += value
    return True


def _record(obj: object, offset: int) -> model.Comment | model.Resolution | model.ParseError:
    if not isinstance(obj, dict):
        return _record_error(offset, "a record is not a JSON object")
    if not _is_unicode(obj):
        return _record_error(offset, "a record holds an escaped surrogate, which isn't text")

    author, at = obj.get("author"), obj.get("at")
    if not isinstance(author, str) or not author:
        return _record_error(offset, "a record has no author")
    if not isinstance(at, str) or model.instant(at) is None:
        return _record_error(offset, "a record's `at` is not an ISO 8601 time in UTC")

    if "resolves" in obj:
        if "id" in obj:
            return _record_error(offset, "a record has both `id` and `resolves`")
        if not isinstance(obj["resolves"], str):
            return _record_error(offset, "a resolution's `resolves` is not an id")
        return model.Resolution(
            resolves=obj["resolves"],
            author=author,
            at=at,
            offset=offset,
            extra={k: v for k, v in obj.items() if k not in _RESOLUTION_FIELDS},
        )

    comment_id, body, re_, span = obj.get("id"), obj.get("body"), obj.get("re"), obj.get("span")
    if not isinstance(comment_id, str) or not model.ID.fullmatch(comment_id):
        return _record_error(offset, "a comment's `id` is missing or not an id")
    if comment_id == model.SECTION_NAME:
        return _record_error(offset, f"`{model.SECTION_NAME}` can't be a comment id")
    if not isinstance(body, str):
        return _record_error(offset, f"comment {comment_id} has no body")
    if re_ is not None and not isinstance(re_, str):
        return _record_error(offset, f"comment {comment_id}'s `re` is not an id")
    if span is not None and not _is_span(span):
        return _record_error(offset, f"comment {comment_id}'s `span` is not [start, end]")
    if span is not None and re_ is None:
        return _record_error(offset, f"comment {comment_id} has a `span` but answers no comment")

    return model.Comment(
        id=comment_id,
        author=author,
        at=at,
        body=body,
        re=re_,
        span=(span[0], span[1]) if span is not None else None,
        offset=offset,
        extra={k: v for k, v in obj.items() if k not in _COMMENT_FIELDS},
    )


def _is_span(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
        and 0 <= value[0] <= value[1]
    )
