"""Bounded descriptions of changes to a Markdown body."""

import difflib
import re

_MAX_HUNKS = 5
_MAX_EXCERPT = 500
_MAX_HEADING = 120
_HEADING = re.compile(r" {0,3}#{1,6}(?:[ \t]+|$)")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text

    return f"{text[:limit]}... ({len(text) - limit} characters omitted)"


def _headings(lines: list[str]) -> list[str]:
    headings: list[str] = []
    heading = "before any heading"
    fence = ""
    for line in lines:
        marker = _FENCE.match(line)
        if marker:
            run = marker.group(1)
            if not fence:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not line[marker.end() :].strip():
                fence = ""
        elif not fence and _HEADING.match(line):
            heading = _shorten(line.strip(), _MAX_HEADING)
        headings.append(heading)
    return headings


def describe(old: str, new: str) -> tuple[str, str]:
    """Return the line-count summary and zero-context hunks in new-body coordinates."""
    old_lines, new_lines = old.splitlines(), new.splitlines()
    changes = [
        (i1, i2, j1, j2)
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines).get_opcodes()
        if tag != "equal"
    ]
    added = sum(j2 - j1 for _, _, j1, j2 in changes)
    removed = sum(i2 - i1 for i1, i2, _, _ in changes)
    headings = _headings(new_lines)
    hunks: list[str] = []
    for i1, i2, j1, j2 in changes[:_MAX_HUNKS]:
        if j1 == j2:
            location = f"after line {j1}"
            heading = headings[j1 - 1] if j1 else "before any heading"
        else:
            location = f"line {j1 + 1}" if j2 == j1 + 1 else f"lines {j1 + 1}-{j2}"
            heading = headings[j1]
        hunks.append(f"{location} [{heading}]; {i2 - i1} removed line(s)")
        if j1 != j2:
            hunks.append(
                _shorten("\n".join(f"+ {line}" for line in new_lines[j1:j2]), _MAX_EXCERPT)
            )
    if len(changes) > _MAX_HUNKS:
        hunks.append(f"{len(changes) - _MAX_HUNKS} more hunk(s) omitted")
    return f"+{added}/-{removed} lines", "\n".join(hunks)
