"""The checker's line protocol: one tab-separated record per line, fields percent-escaped.

The first record is `protocol<TAB>1`. Every other record starts with its kind, and each
kind has a fixed number of fields. Only `%`, tab, CR and LF are escaped, so any other
`%` sequence is malformed rather than passed through.
"""

import re
import typing as ty
from collections import abc

VERSION = "1"

Record = tuple[str, ...]

# Field counts, the kind included.
INPUT: ty.Mapping[str, int] = {"context": 3, "task": 4, "brief": 4, "case": 4, "fact": 7}

DESCRIBE: ty.Mapping[str, int] = {"watch": 3}

EVALUATE: ty.Mapping[str, int] = {
    "ok": 3,
    "wait": 7,
    "unknown": 3,
    "challenge": 7,
    "adjudicate": 7,
    "recheck": 3,
}

_ESCAPES = {"%": "%25", "\t": "%09", "\r": "%0D", "\n": "%0A"}

_UNESCAPES = {code: char for char, code in _ESCAPES.items()}

_ESCAPE = re.compile("[%\t\r\n]")

_PERCENT = re.compile("%(..)?", re.DOTALL)


class ProtocolError(ValueError):
    pass


def escape(value: str) -> str:
    return _ESCAPE.sub(lambda m: _ESCAPES[m.group()], value)


def unescape(value: str) -> str:
    def _one(match: re.Match[str]) -> str:
        if match.group() not in _UNESCAPES:
            raise ProtocolError(f"malformed escape {match.group()!r} in {value!r}")

        return _UNESCAPES[match.group()]

    return _PERCENT.sub(_one, value)


def line(*fields: str) -> str:
    return "\t".join(escape(f) for f in fields) + "\n"


def header() -> str:
    return line("protocol", VERSION)


def _record(number: int, raw: str, arities: ty.Mapping[str, int]) -> Record:
    fields = tuple(unescape(f) for f in raw.split("\t"))
    if fields[0] not in arities:
        raise ProtocolError(f"line {number}: unknown record {fields[0]!r}")

    if len(fields) != arities[fields[0]]:
        raise ProtocolError(
            f"line {number}: {fields[0]} has {len(fields)} fields, expected {arities[fields[0]]}"
        )

    return fields


def parse(text: str, arities: ty.Mapping[str, int]) -> list[Record]:
    """Every record after the header, decoded; raises ProtocolError on anything unexpected."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        raise ProtocolError("no protocol header")

    head = tuple(unescape(f) for f in lines[0].split("\t"))
    if head != ("protocol", VERSION):
        raise ProtocolError(f"unsupported protocol header {lines[0]!r}")

    return [_record(number, raw, arities) for number, raw in enumerate(lines[1:], start=2)]


def render(records: abc.Iterable[abc.Sequence[str]]) -> str:
    return header() + "".join(line(*r) for r in records)
