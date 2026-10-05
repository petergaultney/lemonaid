"""`brief check`: what is wrong with a brief's shape, so a broken edit is caught in its own turn."""

import re
import sqlite3
from collections import abc
from pathlib import Path

from ..lineage import links
from . import identity, layout, now, now_edit, pr_table, questions, status, store

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


def _status(lines: abc.Sequence[str]) -> list[str]:
    header = lines[
        : next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    ]
    values = [m["value"].strip() for line in header if (m := _STATUS.fullmatch(line.strip()))]
    if not values:
        return ["No `Status:` line above the first `## ` section"]

    if len(values) > 1:
        return [f"{len(values)} `Status:` lines; a brief has one"]

    if values[0] not in store.STATES:
        return [f"Status {values[0]!r} is not one word of: {', '.join(store.STATES)}"]

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

    return problems


def question_problems(text: str) -> list[str]:
    parts = status.split(text)
    return [
        f"`### {label}` in ## Questions has no matching bullet under ### Needs Peter"
        for label in questions.unmatched(
            now.parse(parts.now).needs, questions.entries(parts.questions)
        )
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
    problems.extend(_status(lines))
    try:
        identity.read(text)
    except ValueError as e:
        problems.append(str(e))

    if "now" in lowered:
        problems.extend([*_now(now_edit.now_of(text)), *_spacing(lines)])

    if "questions" in lowered:
        problems.extend(question_problems(text))

    if "waiters" in lowered and lowered[-1] != "waiters":
        problems.append("`## Waiters` is not the last section")

    return problems


def recorded(conn: sqlite3.Connection, path: Path, text: str) -> list[str]:
    """Whether the brief's `Lemon-ID` is the one the database records for *path*."""
    try:
        in_file = identity.read(text)
    except ValueError:
        return []  # structure() reports it

    row = conn.execute(
        "SELECT lemon_id FROM lemon_identities WHERE path = ?", (str(path.resolve()),)
    ).fetchone()
    if row and row["lemon_id"] != in_file:
        return [f"Lemon-ID is {in_file or 'missing'}, but this brief is {row['lemon_id']}"]

    if row or not in_file:
        return []

    alias = conn.execute(
        "SELECT lemon_id FROM lemon_aliases WHERE old_id = ?", (in_file,)
    ).fetchone()
    if alias:
        return [f"Lemon-ID {in_file} is an old ID of {alias['lemon_id']}"]

    holder = conn.execute(
        "SELECT path FROM lemon_identities WHERE lemon_id = ?", (in_file,)
    ).fetchone()
    return [f"Lemon-ID {in_file} belongs to {holder['path']}"] if holder else []


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
    return [*structure(text), *recorded(conn, path, text), *parent_line(conn, text)]
