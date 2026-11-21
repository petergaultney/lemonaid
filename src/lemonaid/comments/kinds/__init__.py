"""What each kind of file does its own way: where code is, how markers and the threads
section are spelled, and where a new anchor's markers go.

Each kind is a module whose functions implement `Kind`; everything else in
`lemonaid.comments` calls a kind through it and never branches on which one it is.
"""

import re
import typing as ty

from .. import model, records
from . import markdown, python


class Kind(ty.Protocol):
    def code_regions(self, text: str) -> list[model.CodeRegion]:
        """Where markers are text: strings or code."""
        ...

    def unclosed_string(self, text: str) -> int | None:
        """Where a string that the text never closes starts, for kinds that have them."""
        ...

    def marker_pattern(self) -> re.Pattern[str]:
        """Markers, with `id` and `close` groups."""
        ...

    def marker_carrier(
        self, text: str, match: re.Match[str], body_end: int
    ) -> tuple[int, int] | None:
        """What removing this match removes, or None when the match isn't a marker."""
        ...

    def point_end(self, text: str, start: int, body_end: int) -> int:
        """The end of the text a point anchor starting at `start` covers."""
        ...

    def find_section(
        self, text: str
    ) -> tuple[model.Section | None, list[records.RecordLine], list[model.ParseError]]: ...

    def encode_record(self, json_line: str, newline: str) -> str:
        """A record's line in the threads section, line ending included."""
        ...

    def new_section(self, record_line: str, newline: str) -> str:
        """A threads section holding one record, to append to a file that has none."""
        ...

    def place_anchor(
        self, text: str, start: int, end: int, doc: model.Document, comment_id: str
    ) -> list[model.Edit]:
        """The edits that put a new anchor's markers around `text[start:end]`."""
        ...


_KINDS: ty.Final[dict[model.FileKind, Kind]] = {"python": python, "markdown": markdown}


def get(kind: model.FileKind) -> Kind:
    return _KINDS[kind]
