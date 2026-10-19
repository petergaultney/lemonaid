"""Parse and render the subheadings in a brief's Now section.

ORDER identifies conventional labels; it does not constrain heading order.
"""

import dataclasses
import re
from collections import abc

ORDER = ("needs", "running", "waiting on", "next", "prs", "docs", "lemons", "done")

_NOW_HEADING = re.compile(r"##\s+now\s*", re.IGNORECASE)
_SECTION = re.compile(r"#{1,2}\s")
_SUB_HEADING = re.compile(r"###\s+(?P<heading>.+?)\s*#*\s*")
_NEEDS = re.compile(r"needs(?:\s+\S+)?", re.IGNORECASE)
_BULLET = re.compile(r"[-*+]\s+")
_FENCE = re.compile(r"(```|~~~)")
_HEADER_LINE = re.compile(r"(Parent|Output-Doc|Area|Groups):")


@dataclasses.dataclass(frozen=True)
class Section:
    heading: str  # as written, without the `###`
    body: tuple[str, ...]  # without blank lines at either end


@dataclasses.dataclass(frozen=True)
class Now:
    lead: tuple[str, ...]
    sections: tuple[Section, ...]
    tail: tuple[str, ...]  # `Parent:`, `Output-Doc:`, `Area:` and `Groups:` lines


def rank(heading: str) -> int | None:
    """Where *heading* goes in `ORDER`, or None for a heading the rules don't name."""
    if _NEEDS.fullmatch(heading.strip()):
        return 0

    plain = heading.strip().lower()
    return ORDER.index(plain) if plain in ORDER else None


def trimmed(lines: abc.Sequence[str]) -> tuple[str, ...]:
    start = next((i for i, line in enumerate(lines) if line.strip()), len(lines))
    end = next((i + 1 for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), start)
    return tuple(lines[start:end])


def bounds(lines: abc.Sequence[str]) -> tuple[int, int] | None:
    """The line range of the `## Now` body in a brief's lines, or None without one."""
    start = next((i for i, line in enumerate(lines) if _NOW_HEADING.fullmatch(line)), None)
    if start is None:
        return None

    in_fence = False
    for i in range(start + 1, len(lines)):
        if _FENCE.match(lines[i]):
            in_fence = not in_fence
        elif not in_fence and _SECTION.match(lines[i]):
            return start + 1, i

    return start + 1, len(lines)


def is_field(line: str) -> bool:
    """Whether *line* is a `Parent:`, `Output-Doc:`, `Area:` or `Groups:` line."""
    return bool(_HEADER_LINE.match(line))


def parse(body: str) -> Now:
    lead: list[str] = []
    tail: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _SUB_HEADING.fullmatch(line)
        if heading:
            sections.append((heading["heading"], []))
        elif is_field(line) and not in_fence:
            tail.append(line)
        else:
            (sections[-1][1] if sections else lead).append(line)

    return Now(
        trimmed(lead),
        tuple(Section(heading, trimmed(lines)) for heading, lines in sections),
        tuple(tail),
    )


def find(now: Now, heading: str) -> int | None:
    """The index of the section with the same heading text, ignoring case."""
    return next(
        (
            i
            for i, section in enumerate(now.sections)
            if section.heading.strip().lower() == heading.strip().lower()
        ),
        None,
    )


def ordered(now: Now) -> Now:
    """*now* with its known sub-headings in order and empty ones gone.

    A heading the rules don't name sorts with the known heading above it, after it.
    """
    keys: list[int] = []
    for section in now.sections:
        keys.append(r if (r := rank(section.heading)) is not None else (keys[-1] if keys else -1))

    kept = sorted(
        ((key, section) for key, section in zip(keys, now.sections, strict=True) if section.body),
        key=lambda pair: pair[0],
    )
    return dataclasses.replace(now, sections=tuple(section for _, section in kept))


def render(now: Now) -> str:
    blocks = [
        *(["\n".join(now.lead)] if now.lead else []),
        *(f"### {s.heading}\n\n" + "\n".join(s.body) for s in now.sections),
        *now.tail,
    ]
    return "\n\n".join(blocks)


def bullets(body: abc.Sequence[str]) -> list[tuple[str, ...]]:
    """*body* as items: each top-level bullet with the lines under it, and any lines before one."""
    items: list[list[str]] = []
    for line in body:
        if _BULLET.match(line) or not items:
            items.append([line])
        else:
            items[-1].append(line)

    return [tuple(item) for item in items]


def bullet_text(item: abc.Sequence[str]) -> str:
    """The text of an item's first line after its bullet marker, or "" when it isn't a bullet."""
    match = _BULLET.match(item[0])
    return item[0][match.end() :] if match else ""
