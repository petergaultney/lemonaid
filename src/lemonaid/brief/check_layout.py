"""Text-only shape checks for brief headers and legacy Now sections."""

import re
from collections import abc

from . import doc_table, layout, lemon_table, pr_table, store

_HEADING = re.compile(r"(?P<level>#{1,2})\s+(?P<text>.*?)\s*#*\s*")
_FENCE = re.compile(r"(```|~~~)")
_STATUS = re.compile(r"status:\s*(?P<value>.*)", re.IGNORECASE)


def headings(lines: abc.Sequence[str]) -> list[tuple[int, str]]:
    """(level, text) of each `#` and `##` heading outside code fences."""
    found = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and (match := _HEADING.fullmatch(line)):
            found.append((len(match["level"]), match["text"]))

    return found


def stray_ticks(lines: abc.Sequence[str]) -> list[str]:
    """A `#` or `##` heading line with an unpaired backtick, which is prose cut at a line start."""
    found = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and _HEADING.fullmatch(line) and line.count("`") % 2:
            found.append(f"`{line.strip()}` is a heading line with an unpaired backtick")

    return found


def status_problems(lines: abc.Sequence[str]) -> list[str]:
    header = lines[
        : next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    ]
    values = [m["value"].strip() for line in header if (m := _STATUS.fullmatch(line.strip()))]
    if len(values) > 1:
        return [f"{len(values)} `Status:` lines; a brief has one"]

    if values and values[0] not in (*store.STATES, *store.RETIRED):
        return [
            f"Status {values[0]!r} is not one word of: {', '.join(store.STATES)};"
            " leave it out to show the lemon's own state"
        ]

    return []


def spacing(lines: abc.Sequence[str]) -> list[str]:
    """A `###` heading in `## Now` without a blank line above and below it."""
    start, end = layout.bounds(lines) or (0, 0)
    headings = []
    in_fence = False
    for i in range(start, end):
        if _FENCE.match(lines[i]):
            in_fence = not in_fence
        elif not in_fence and lines[i].startswith("### "):
            headings.append(i)

    return [
        f"`{lines[i].strip()}` in ## Now needs a blank line around it"
        for i in headings
        if lines[i - 1].strip() or (i + 1 < len(lines) and lines[i + 1].strip())
    ]


def now_problems(now: layout.Now) -> list[str]:
    problems = []
    seen: set[str] = set()
    for section in now.sections:
        rank = layout.rank(section.heading)
        key = section.heading.strip().lower()
        if key in seen:
            detail = (
                "; Needs headings must have different names (case-insensitive)" if rank == 0 else ""
            )
            problems.append(f"`### {section.heading}` appears twice in ## Now{detail}")
        seen.add(key)
        if not section.body:
            problems.append(f"`### {section.heading}` in ## Now is empty")
        if rank == layout.ORDER.index("prs") and section.body:
            rows, table_problems = pr_table.parse(section.body)
            problems.extend(table_problems or ([] if rows else ["### PRs: the table has no rows"]))

        if section.heading.lower() == "docs":
            problems.extend(doc_table.parse(section.body)[1])
        if section.heading.lower() == "lemons":
            problems.extend(lemon_table.parse(section.body)[1])

    return problems
