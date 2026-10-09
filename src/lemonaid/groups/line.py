"""A brief's `Groups:` line: the copy of its memberships that travels with the file.

The line sits in the header, above the first `##` heading, after `Status:` and
any `Parent:` or `Area:` line. Names are separated by commas, which is why a
group name can't contain one.
"""

import re
from collections import abc

_LINE = re.compile(r"Groups:(?P<names>.*)")
_SECTION = re.compile(r"#{1,2}\s")
_FENCE = re.compile(r"(```|~~~)")
_ANCHOR = re.compile(r"(Status|Parent|Area|Brief-ID|Lemon-ID):", re.IGNORECASE)


def _header_end(lines: abc.Sequence[str]) -> int:
    return next(
        (i for i, line in enumerate(lines) if _SECTION.match(line) and not line.startswith("# ")),
        len(lines),
    )


def _line_index(lines: abc.Sequence[str]) -> int | None:
    in_fence = False
    for i, line in enumerate(lines[: _header_end(lines)]):
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and _LINE.fullmatch(line.rstrip()):
            return i

    return None


def render(names: abc.Iterable[str]) -> str:
    """The line for *names*, or "" for none."""
    joined = ", ".join(names)
    return f"Groups: {joined}" if joined else ""


def read(text: str) -> tuple[str, ...] | None:
    """The names on *text*'s `Groups:` line, or None when it has no line."""
    lines = text.splitlines()
    at = _line_index(lines)
    if at is None:
        return None

    match = _LINE.fullmatch(lines[at].rstrip())
    assert match
    return tuple(name.strip() for name in match["names"].split(",") if name.strip())


def written(text: str, names: abc.Sequence[str]) -> str:
    """*text* with its `Groups:` line naming *names*, or without one when there are none."""
    lines = text.splitlines()
    line = render(names)
    at = _line_index(lines)
    if at is not None:
        replaced = [*lines[:at], *([line] if line else []), *lines[at + 1 :]]
        return "\n".join(replaced).rstrip("\n") + "\n"

    if not line:
        return text

    header = lines[: _header_end(lines)]
    after = next(
        (i + 1 for i in range(len(header) - 1, -1, -1) if _ANCHOR.match(header[i])),
        len(header),
    )
    return "\n".join([*lines[:after], line, *lines[after:]]).rstrip("\n") + "\n"
