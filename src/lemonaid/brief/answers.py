"""Live answers as ordinary, editable Markdown sections."""

import datetime
from pathlib import Path

from . import answer_archive, sections


def _heading(text: str) -> sections.Heading | None:
    return next(
        (h for h in sections.scan(text) if h.level == 2 and h.name.casefold() == "answers"),
        None,
    )


def _quote(text: str) -> str:
    return "\n".join(f"> {line}".rstrip() for line in text.strip().splitlines())


def add(text: str, question: str, answer: str, when: datetime.datetime) -> str:
    if not question.strip() or not answer.strip():
        raise ValueError("The question and answer must both contain text")

    entry = (
        f"### {when.isoformat(sep=' ', timespec='microseconds')}\n\n"
        f"**Question:**\n\n{_quote(question)}\n\n**Answer:**\n\n{_quote(answer)}"
    )
    heading = _heading(text)
    if heading:
        return sections.replace(text, heading, [entry, "", *sections.body(text, heading)])

    headings = sections.scan(text)
    previous = next(
        (
            h
            for name in ("questions", "now")
            for h in headings
            if h.level == 2 and h.name.casefold() == name
        ),
        None,
    )
    at = (
        previous.end
        if previous
        else next((h.start for h in headings if h.level == 2), len(text.splitlines()))
    )
    lines = text.splitlines()
    return "\n".join([*lines[:at], "## Answers", "", entry, "", *lines[at:]]).rstrip() + "\n"


def take(text: str, count: int | None) -> tuple[str, list[str]]:
    """Remove the first count entries, preserving any prose above them."""
    if count is not None and count < 1:
        raise ValueError("Count must be at least 1")

    heading = _heading(text)
    if heading is None:
        return text, []

    body = "\n".join(sections.body(text, heading))
    starts = [h.start for h in sections.scan(body) if h.level == 3]
    lines = body.splitlines()
    entries = [
        "\n".join(lines[a:b]).strip()
        for a, b in zip(starts, [*starts[1:], len(lines)], strict=False)
    ]
    chosen = entries[:count]
    if not chosen:
        return text, []

    remaining = lines[: starts[0]] + ["\n\n".join(entries[len(chosen) :])]
    return sections.replace(text, heading, remaining), chosen


def display(text: str, path: Path) -> tuple[str, str]:
    """The brief without Answers, and their rendered live view with archive count."""
    heading = _heading(text)
    body = "\n".join(sections.body(text, heading)) if heading else ""
    try:
        count = len(answer_archive.read(path))
        notice = (
            f"{count} archived. Use `lemonaid brief answers expand --self` to read them."
            if count
            else ""
        )
    except (OSError, ValueError):
        notice = "Answer archive could not be read."
    rendered = "\n\n".join(
        part for part in ("## Answers" if body or notice else "", notice, body) if part
    )
    return sections.replace(text, heading, (), remove=True) if heading else text, rendered
