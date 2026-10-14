"""A doc body with its layout removed, so reformatting alone never counts as a change.

Runs of whitespace collapse to one space and the spaces around a table's pipes go, so
re-padding a Markdown table (as Obsidian does) changes nothing; so does lengthening the
dashes of its separator row.
"""

import re

_SEPARATOR_ROW = re.compile(r"^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*\|?\s*$")
_DASHES = re.compile(r"-{3,}")
_AROUND_PIPE = re.compile(r"[ \t]*\|[ \t]*")
_WHITESPACE = re.compile(r"\s+")


def normalized(body: str) -> str:
    lines = (
        _DASHES.sub("---", line) if _SEPARATOR_ROW.match(line) else line
        for line in body.splitlines()
    )
    return _WHITESPACE.sub(" ", _AROUND_PIPE.sub("|", "\n".join(lines))).strip()
