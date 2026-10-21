"""`brief check`: what is wrong with a brief's shape, so a broken edit is caught in its own turn."""

import re
import sqlite3
from pathlib import Path

from ..lineage import links
from . import (
    check_identity,
    check_layout,
    doc_table,
    frontmatter,
    frontmatter_check,
    identity,
    name_words,
    now,
    now_edit,
    pr_table,
    questions,
    sections,
    status,
)


def question_problems(text: str) -> list[str]:
    text = frontmatter.legacy(text)
    parts = status.split(text)
    found = now.parse(parts.now)
    return [
        f"`### {label}` in ## Questions has no matching bullet under ### {found.needs_label}"
        for label in questions.unmatched(found.needs, questions.entries(parts.questions))
    ]


def structure(text: str) -> list[str]:
    """Everything wrong with *text* as a brief that the text alone can show."""
    found = frontmatter_check.problems(text)
    text = frontmatter.legacy(text)
    lines = text.splitlines()
    headings = check_layout.headings(lines)
    titles = [heading for level, heading in headings if level == 1]
    section_names = [heading for level, heading in headings if level == 2]
    lowered = [heading.lower() for heading in section_names]
    problems = [
        *found,
        *([] if len(titles) == 1 else [f"{len(titles)} `# ` title lines; a brief has one"]),
    ]
    problems.extend(
        f"`## {name}` appears {lowered.count(name.lower())} times"
        for name in dict.fromkeys(section_names)
        if lowered.count(name.lower()) > 1
        and lowered.index(name.lower()) == section_names.index(name)
    )
    problems.extend(check_layout.stray_ticks(lines))
    problems.extend(check_layout.status_problems(lines))
    try:
        identity.read(text)
    except ValueError as e:
        problems.append(str(e))

    if "now" in lowered:
        problems.extend(
            [*check_layout.now_problems(now_edit.now_of(text)), *check_layout.spacing(lines)]
        )

    for section in sections.behavior(text):
        if section.heading.lower() == "prs":
            problems.extend(pr_table.parse(section.body)[1])
        elif section.heading.lower() == "docs":
            problems.extend(doc_table.parse(section.body)[1])

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
    text = frontmatter.legacy(text)
    lines = text.splitlines()
    parts = status.split(text)
    headings = [heading.lower() for level, heading in check_layout.headings(lines) if level == 2]
    advice = []
    old = [
        h.name
        for h in sections.scan(text)
        if h.level == 3 and h.parent.lower() == "now" and h.name.lower() in sections.PROMOTED
    ]
    if old:
        advice.append(
            f"Old-layout headings under ## Now: {', '.join(old)}; use `lemonaid brief migrate --self` (or --all)"
        )
    if parts.status == "done" and "executive summary of results" in headings and not parts.summary:
        advice.append("`## Executive Summary of Results` is empty on a done brief")
    return advice


def has_parent_line(text: str) -> bool:
    in_fence = False
    for line in frontmatter.legacy(text).splitlines():
        if re.match(r"(```|~~~)", line):
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
