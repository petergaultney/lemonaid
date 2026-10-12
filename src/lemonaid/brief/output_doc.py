"""A brief's `Output-Doc:` line: the document its lemon's work produces, if one was named."""

import re
from pathlib import Path

_LINE = re.compile(r"Output-Doc:\s*(?P<path>.+?)\s*")
_FENCE = re.compile(r"(```|~~~)")


def read(text: str) -> Path | None:
    """The path on *text*'s header `Output-Doc:` line, or None without one."""
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        elif line.startswith("## "):
            return None
        elif not in_fence and (match := _LINE.fullmatch(line)):
            return Path(match["path"]).expanduser()

    return None


def of_brief(brief: Path) -> Path | None:
    """The output doc recorded in the brief file *brief*."""
    return read(brief.read_text())
