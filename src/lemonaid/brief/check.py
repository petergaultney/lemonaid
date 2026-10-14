"""`brief check`: what is wrong with a brief's shape, so a broken edit is caught in its own turn."""

import re
import sqlite3
from collections import abc
from pathlib import Path

from ..lineage import links
from . import (
    check_identity,
    doc_table,
    identity,
    layout,
    name_words,
    now,
    now_edit,
    pr_table,
    questions,
    status,
    store,
)

_HEADING = re.compile(r"(?P<level>#{1,2})\s+(?P<text>.*?)\s*#*\s*")
_FENCE = re.compile(r"(```|~~~)")
_STATUS = re.compile(r"status:\s*(?P<value>.*)", re.IGNORECASE)


def _headings(lines: abc.Sequence[str]) -> list[tuple[int, str]]:
    """(level, text) of each `#` and `##` heading outside code fences."""
    found = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and (match := _HEADING.fullmatch(line)):
            found.append((len(match["level"]), match["text"]))

    return found


def _stray_ticks(lines: abc.Sequence[str]) -> list[str]:
    """A `#` or `##` heading line with an unpaired backtick, which is prose cut at a line start."""
    found = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and _HEADING.fullmatch(line) and line.count("`") % 2:
            found.append(f"`{line.strip()}` is a heading line with an unpaired backtick")

    return found


def _status(lines: abc.Sequence[str]) -> list[str]:
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


def _spacing(lines: abc.Sequence[str]) -> list[str]:
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


def _now(now: layout.Now) -> list[str]:
    problems = []
    seen: dict[object, str] = {}
    last_rank = -1
    for section in now.sections:
        rank = layout.rank(section.heading)
        key = rank if rank is not None else section.heading.strip().lower()
        if key in seen:
            problems.append(f"`### {section.heading}` appears twice in ## Now")
        seen[key] = section.heading
        if rank is not None and rank < last_rank:
            problems.append(f"`### {section.heading}` is out of order in ## Now")
        last_rank = max(last_rank, rank if rank is not None else -1)
        if not section.body:
            problems.append(f"`### {section.heading}` in ## Now is empty")
        if rank == layout.ORDER.index("prs") and section.body:
            rows, table_problems = pr_table.parse(section.body)
            problems.extend(table_problems or ([] if rows else ["### PRs: the table has no rows"]))

        if section.heading.lower() == "docs":
            problems.extend(doc_table.parse(section.body)[1])

    return problems


def question_problems(text: str) -> list[str]:
    parts = status.split(text)
    found = now.parse(parts.now)
    return [
        f"`### {label}` in ## Questions has no matching bullet under ### {found.needs_label}"
        for label in questions.unmatched(found.needs, questions.entries(parts.questions))
    ]


def structure(text: str) -> list[str]:
    """Everything wrong with *text* as a brief that the text alone can show."""
    lines = text.splitlines()
    headings = _headings(lines)
    titles = [heading for level, heading in headings if level == 1]
    sections = [heading for level, heading in headings if level == 2]
    lowered = [heading.lower() for heading in sections]
    problems = [] if len(titles) == 1 else [f"{len(titles)} `# ` title lines; a brief has one"]
    problems.extend(
        f"`## {name}` appears {lowered.count(name.lower())} times"
        for name in dict.fromkeys(sections)
        if lowered.count(name.lower()) > 1 and lowered.index(name.lower()) == sections.index(name)
    )
    problems.extend(_stray_ticks(lines))
    problems.extend(_status(lines))
    try:
        identity.read(text)
    except ValueError as e:
        problems.append(str(e))

    if "now" in lowered:
        problems.extend([*_now(now_edit.now_of(text)), *_spacing(lines)])

    if "questions" in lowered:
        problems.extend(question_problems(text))

    watching = [h for h in lowered if h in {"watching", "waiters"}]
    if len(watching) > 1:
        problems.append("Use one `## Watching` section (or legacy `## Waiters`), not both")
    if watching and lowered[-1] != watching[0]:
        problems.append(f"`## {watching[0].title()}` is not the last section")

    return problems


def warnings(text: str) -> list[str]:
    """Advice that does not make a brief invalid or refuse edits."""
    lines = text.splitlines()
    parts = status.split(text)
    headings = [heading.lower() for level, heading in _headings(lines) if level == 2]
    if parts.status == "done" and "executive summary of results" in headings and not parts.summary:
        return ["`## Executive Summary of Results` is empty on a done brief"]
    return []


def has_parent_line(text: str) -> bool:
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and line.startswith("Parent:"):
            return True

    return False


def parent_line(conn: sqlite3.Connection, text: str) -> list[str]:
    """A missing `Parent:` line, when the database records a parent for the brief."""
    try:
        lemon_id = identity.read(text)
    except ValueError:
        return []  # structure() reports it

    parent = links.parent_of(conn, lemon_id) if lemon_id else ""
    if not parent or has_parent_line(text):
        return []

    return [f"No `Parent:` line, but {parent} is this brief's parent; add `Parent: {parent}`"]


def problems(conn: sqlite3.Connection, path: Path, text: str) -> list[str]:
    return [
        *structure(text),
        *check_identity.recorded(conn, path, text),
        *parent_line(conn, text),
        *check_identity.groups_line(conn, text),
        *name_words.problems(text),
    ]


# Kept for callers of the existing check API.
recorded = check_identity.recorded
groups_line = check_identity.groups_line
