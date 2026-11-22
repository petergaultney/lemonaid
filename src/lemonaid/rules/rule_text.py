"""The paragraph or list item that states a rule, found by the text it starts with."""

import re
import textwrap
from collections import abc
from pathlib import Path

from ..log import get_logger

_log = get_logger("rules.rule_text")

_LIST_ITEM = re.compile(r"\s*(?:[-*+]|\d+[.)])\s")
_HEADING = re.compile(r"\s*#{1,6}\s")
_LONGEST = 2000  # characters quoted to a lemon; a rule longer than this is cut


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def starts(text: str, rule_starts: str) -> list[int]:
    """The lines of *text* that begin, after indentation, with *rule_starts*."""
    return [
        number
        for number, line in enumerate(text.splitlines())
        if line.lstrip().startswith(rule_starts)
    ]


def _block(lines: abc.Sequence[str], first: int) -> abc.Iterator[str]:
    """The line at *first* and what continues it: its wrapped lines and nested items."""
    yield lines[first]
    for line in lines[first + 1 :]:
        if not line.strip() or _HEADING.match(line):
            return

        if _LIST_ITEM.match(line) and _indent(line) <= _indent(lines[first]):
            return

        yield line


def quote(text: str, rule_starts: str) -> str:
    """The first paragraph or list item in *text* that begins with *rule_starts*, or ""."""
    found = starts(text, rule_starts)
    if not found:
        return ""

    lines = text.splitlines()
    rule = textwrap.dedent("\n".join(_block(lines, found[0]))).strip()
    return rule if len(rule) <= _LONGEST else rule[: _LONGEST - 3].rstrip() + "..."


def read(path: Path, rule_starts: str) -> str:
    """The rule's text, read fresh from *path*; "" when the file or the rule is gone."""
    try:
        return quote(path.read_text(), rule_starts)
    except OSError as error:
        _log.warning("cannot read rule file %s: %s", path, error)
        return ""
