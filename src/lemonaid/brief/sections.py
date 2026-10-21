"""Heading ranges shared by generic edits and old/new brief layout readers."""

import dataclasses
import re
from collections import abc

from . import frontmatter, layout

PROMOTED = ("next", "prs", "docs", "done")
_HEADING = re.compile(r"(?P<marks>#{1,6})\s+(?P<name>.+?)\s*#*\s*")
_FENCE = re.compile(r" {0,3}(?P<marks>`{3,}|~{3,})")


@dataclasses.dataclass(frozen=True)
class Heading:
    name: str
    level: int
    start: int
    end: int
    direct_end: int
    parent: str


def unfenced_lines(text: str) -> abc.Iterator[tuple[int, str]]:
    """Each line outside code fences and outside the frontmatter block, with its index."""
    block, _ = frontmatter.split(text)
    skip = len(block) + 2 if block is not None else 0
    fence = ""
    for i, line in enumerate(text.splitlines()):
        if i < skip:
            continue

        if match := _FENCE.match(line):
            marks = match["marks"]
            if not fence:
                fence = marks
            elif (
                marks[0] == fence[0]
                and len(marks) >= len(fence)
                and not line[match.end() :].strip()
            ):
                fence = ""
        elif not fence:
            yield i, line


def scan(text: str) -> list[Heading]:
    length = len(text.splitlines())
    found = [
        (i, match["name"], len(match["marks"]))
        for i, line in unfenced_lines(text)
        if (match := _HEADING.fullmatch(line))
    ]
    return [
        Heading(
            name,
            level,
            start,
            next((s for s, _, depth in found[j + 1 :] if depth <= level), length),
            found[j + 1][0] if j + 1 < len(found) else length,
            next((n for _, n, depth in reversed(found[:j]) if depth < level), ""),
        )
        for j, (start, name, level) in enumerate(found)
    ]


def find(text: str, name: str) -> Heading | None:
    matches = [h for h in scan(text) if h.name.casefold() == name.strip().casefold()]
    if len(matches) > 1:
        candidates = ", ".join(
            f"{'#' * h.level} {h.name} (under {h.parent or 'header'}, line {h.start + 1})"
            for h in matches
        )
        raise ValueError(f"Ambiguous heading {name!r}: {candidates}")
    return matches[0] if matches else None


def metadata_indices(text: str) -> set[int]:
    now = next((h for h in scan(text) if h.level == 2 and h.name.lower() == "now"), None)
    if now is None:
        return set()

    return {
        i for i, line in unfenced_lines(text) if now.start < i < now.end and layout.is_field(line)
    }


def body(text: str, heading: Heading, *, direct: bool = False) -> tuple[str, ...]:
    metadata = metadata_indices(text)
    end = heading.direct_end if direct else heading.end
    return layout.trimmed(
        [
            line
            for i, line in enumerate(text.splitlines())
            if heading.start < i < end and i not in metadata
        ]
    )


def behavior(text: str) -> tuple[layout.Section, ...]:
    return tuple(
        layout.Section(h.name, body(text, h))
        for h in scan(text)
        if h.level == 2 or (h.level == 3 and h.parent.lower() == "now")
    )


def replace(
    text: str,
    heading: Heading,
    lines: abc.Sequence[str],
    *,
    remove: bool = False,
    direct: bool = False,
) -> str:
    source = text.splitlines()
    end = heading.direct_end if direct else heading.end
    fields = [source[i] for i in sorted(metadata_indices(text)) if heading.start < i < end]
    replacement = [] if remove else [source[heading.start], "", *lines, ""]
    return (
        "\n".join(
            [
                *source[: heading.start],
                *replacement,
                *fields,
                *([""] if fields else []),
                *source[end:],
            ]
        ).rstrip()
        + "\n"
    )


def insert(
    text: str, name: str, lines: abc.Sequence[str], level: int = 2, parent: str = "Now"
) -> str:
    if not name.strip() or "\n" in name or name.lstrip().startswith("#"):
        raise ValueError("Give a heading name without # marks or newlines")
    if level not in range(2, 7):
        raise ValueError("Heading level must be between 2 and 6")
    headings = scan(text)
    if level > 2:
        container = find(text, parent)
        if container is None or container.level >= level:
            raise ValueError(f"A level {level} heading needs an existing parent above that level")
        at = next(
            (
                h.start
                for h in headings
                if container.start < h.start < container.end and h.level < level
            ),
            container.end,
        )
    else:
        at = next(
            (
                h.start
                for h in headings
                if h.level == 2 and h.name.lower() in {"watching", "waiters"}
            ),
            len(text.splitlines()),
        )
    source = text.splitlines()
    above = source[:at]
    while above and not above[-1].strip():
        above.pop()
    return (
        "\n".join(
            [*above, "", f"{'#' * level} {name.strip()}", "", *lines, "", *source[at:]]
        ).rstrip()
        + "\n"
    )


def projected(text: str) -> str:
    """A read-only legacy-shaped view for the brief renderer."""
    headings = [h for h in scan(text) if h.level == 2 and h.name.lower() in PROMOTED]
    if not headings:
        return text
    extra = "\n\n".join(f"### {h.name}\n\n" + "\n".join(body(text, h)) for h in headings)
    source = text.splitlines()
    for h in reversed(headings):
        del source[h.start : h.end]
    remaining = "\n".join(source)
    now = next((h for h in scan(remaining) if h.level == 2 and h.name.lower() == "now"), None)
    if now:
        return replace(remaining, now, (*body(remaining, now), "", *extra.splitlines()))
    return insert(remaining, "Now", extra.splitlines())
