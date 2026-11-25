"""The text a delivery would carry: a doc without its frontmatter, or one of its sections.

A section is its heading line and everything up to the next heading of the same or a
higher level, outside fenced code. Headings match ignoring case.
"""

import re

_HEADING = re.compile(r"(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")


def without_frontmatter(text: str) -> str:
    """*text* less a leading frontmatter block."""
    lines = text.split("\n")
    if lines[0].rstrip() != "---":
        return text

    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() in ("---", "...")), None)
    return text if end is None else "\n".join(lines[end + 1 :])


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line, level, title) of each heading outside fenced code."""
    found, fence = [], ""
    for number, line in enumerate(lines):
        if fence:
            if line.strip().startswith(fence):
                fence = ""
            continue

        if opened := _FENCE.match(line):
            fence = opened.group(1)
        elif heading := _HEADING.fullmatch(line):
            found.append((number, len(heading.group(1)), heading.group(2)))
    return found


def text(doc: str, section: str = "") -> str:
    """*doc*'s body, or its section headed *section*; "" when it has no such section."""
    body = without_frontmatter(doc).strip("\n")
    if not section:
        return body

    lines = body.split("\n")
    headings = _headings(lines)
    start = next((h for h in headings if h[2].casefold() == section.casefold()), None)
    if start is None:
        return ""

    end = next((n for n, level, _ in headings if n > start[0] and level <= start[1]), len(lines))
    return "\n".join(lines[start[0] : end]).strip("\n")
