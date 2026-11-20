"""The types of a file's review comments, read by `parse`."""

import dataclasses
import datetime as dt
import re
import typing as ty

FileKind = ty.Literal["python", "markdown"]


ID: ty.Final = re.compile(r"[A-Za-z][\w-]*")


SECTION_NAME: ty.Final = "threads"


_KIND_BY_SUFFIX: ty.Final[dict[str, FileKind]] = {
    ".py": "python",
    ".md": "markdown",
    ".markdown": "markdown",
}


class Edit(ty.NamedTuple):
    """Replace `[start, end)` of a file's text with `text`."""

    start: int
    end: int
    text: str


class CodeRegion(ty.NamedTuple):
    """A Python string or Markdown code, where markers are text. A block region spans
    lines (a fenced block, a multi-line string); an inline one is a code span."""

    start: int
    end: int
    block: bool


ErrorKind = ty.Literal["section", "record", "anchor", "link", "string"]


class ParseError(ty.NamedTuple):
    """`kind` says which part of the format the error is in: the section's frame, a record
    in it, an anchor's markers, a link between records, or a Python string."""

    offset: int
    message: str
    kind: ErrorKind


class Marker(ty.NamedTuple):
    """One `[lma:id]` or `[/lma:id]`, and the text that removing it removes (see
    `_carrier`)."""

    id: str
    closing: bool
    carrier: tuple[int, int]


class Anchor(ty.NamedTuple):
    """The text a thread is about, from the end of the opening carrier to the start of the
    closing one. A point anchor has no closing carrier."""

    id: str
    start: int
    end: int
    opening: tuple[int, int]
    closing: tuple[int, int] | None


@dataclasses.dataclass(frozen=True)
class Comment:
    id: str
    author: str
    at: str
    body: str
    re: str | None = None
    span: tuple[int, int] | None = None
    offset: int = 0  # where the record's line starts
    extra: dict[str, ty.Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Resolution:
    resolves: str
    author: str
    at: str
    offset: int = 0
    extra: dict[str, ty.Any] = dataclasses.field(default_factory=dict)


class Section(ty.NamedTuple):
    """The threads section. `start` is where the body ends, including the newline we put
    before the header; `insert_at` is where the next record goes; `end` is where the
    section ends, which is the end of the file unless text follows a Markdown section."""

    start: int
    insert_at: int
    end: int
    closed: bool  # False for a Markdown section with no closing -->


@dataclasses.dataclass(frozen=True)
class Document:
    kind: FileKind
    markers: tuple[Marker, ...]
    anchors: tuple[Anchor, ...]
    comments: tuple[Comment, ...]
    resolutions: tuple[Resolution, ...]
    errors: tuple[ParseError, ...]
    section: Section | None
    newline: str
    unclosed_string: int | None = None  # where a Python string the file never closes starts

    def comment(self, comment_id: str) -> Comment | None:
        return next((c for c in self.comments if c.id == comment_id), None)

    def anchor(self, anchor_id: str) -> Anchor | None:
        return next((a for a in self.anchors if a.id == anchor_id), None)


@dataclasses.dataclass(frozen=True)
class Node:
    comment: Comment
    replies: tuple["Node", ...]
    resolved: bool  # this comment, or one it answers, was resolved


class Thread(ty.NamedTuple):
    anchor: Anchor | None  # None for an orphan, whose anchor is gone
    root: Node


def file_kind(path: str) -> FileKind | None:
    suffix = path[path.rfind(".") :].lower() if "." in path else ""
    return _KIND_BY_SUFFIX.get(suffix)


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def instant(value: str) -> dt.datetime | None:
    """`value` as a time, or None unless it is ISO 8601 with a UTC offset of zero."""
    try:
        instant = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if instant.tzinfo is None or instant.utcoffset() != dt.timedelta(0):
        return None
    return instant
