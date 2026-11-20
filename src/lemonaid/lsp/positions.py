"""Offsets into a document's text as LSP positions, and back.

LSP counts lines at `\\n`, `\\r\\n` and `\\r`, the same line endings `listing.line_starts`
splits at, and counts columns in the encoding the client and server agreed on: UTF-16 code
units unless the client offered UTF-8 or UTF-32.
"""

import bisect
import typing as ty

from ..comments import listing

Encoding = ty.Literal["utf-8", "utf-16", "utf-32"]


class Position(ty.NamedTuple):
    line: int
    character: int


class Codec:
    def __init__(self, text: str, encoding: Encoding = "utf-16") -> None:
        self._text = text
        self._encoding = encoding
        self._starts = listing.line_starts(text)

    def position(self, offset: int) -> Position:
        line = bisect.bisect_right(self._starts, offset) - 1
        return Position(line, _units(self._text[self._starts[line] : offset], self._encoding))

    def offset(self, position: Position) -> int:
        """A position past the end of its line is the end of that line, and a line past the
        end of the text is the end of the text, as LSP asks."""
        if position.line >= len(self._starts):
            return len(self._text)
        start = self._starts[position.line]
        next_start = (
            self._starts[position.line + 1]
            if position.line + 1 < len(self._starts)
            else len(self._text)
        )
        line_text = self._text[start:next_start].rstrip("\r\n")
        units = 0
        for index, character in enumerate(line_text):
            if units >= position.character:
                return start + index
            units += _units(character, self._encoding)
        return start + len(line_text)


def _units(text: str, encoding: Encoding) -> int:
    match encoding:
        case "utf-32":
            return len(text)
        case "utf-16":
            return len(text) + sum(ord(c) > 0xFFFF for c in text)
        case "utf-8":
            return len(text.encode("utf-8", "surrogatepass"))
    raise ValueError(f"unknown position encoding {encoding!r}")
