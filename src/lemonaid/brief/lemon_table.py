"""Lemons a lemon watches besides its children, listed under `### Lemons`.

A row names a lemon by Lemon-ID, channel or brief name. The Watch cell lists the Statuses
that wake the watcher, with `needs` for a change of the lemon's Needs; empty means the
default (`merge`, `done` and `needs`). An exit, a gone session or place, and a deaf or dead
lemon always wake.
"""

import dataclasses
import re
from collections import abc

from . import now_edit, store

NEEDS = "needs"
DEFAULT = (*("merge", "done"), NEEDS)
_HEADER = ["lemon", "purpose", "watch"]
_PIPE = re.compile(r"(?<!\\)\|")


@dataclasses.dataclass(frozen=True)
class Row:
    lemon: str
    purpose: str = ""
    watch: tuple[str, ...] = ()  # as written; empty means DEFAULT

    @property
    def wake(self) -> tuple[str, ...]:
        return self.watch or DEFAULT


def _words(cell: str) -> tuple[tuple[str, ...], str]:
    """The Watch cell's words, and what is wrong with them."""
    words = tuple(w.strip().lower() for w in cell.split(",") if w.strip())
    unknown = [w for w in words if w not in (*store.STATES, NEEDS)]
    return words, f"{', '.join(unknown)} is not a status or `needs`" if unknown else ""


def parse(body: abc.Sequence[str]) -> tuple[list[Row], list[str]]:
    lines = [line.strip() for line in body if line.strip()]
    if not lines:
        return [], []

    split = [
        [c.strip().replace("\\|", "|") for c in _PIPE.split(line.strip("|"))] for line in lines
    ]
    if [c.lower() for c in split[0]] != _HEADER:
        return [], ["### Lemons: use `| Lemon | Purpose | Watch |`"]

    problems = []
    if len(split) < 2 or not all(re.fullmatch(r":?-+:?", c) for c in split[1]):
        problems.append("### Lemons: the header needs a separator line")
    rows: list[Row] = []
    for line, cells in zip(lines[2:], split[2:], strict=True):
        if len(cells) != 3 or not cells[0]:
            problems.append(f"### Lemons: invalid lemon row: {line}")
            continue

        words, problem = _words(cells[2])
        if problem:
            problems.append(f"### Lemons: {problem}")
            continue

        if any(row.lemon == cells[0] for row in rows):
            problems.append(f"### Lemons: {cells[0]} has two rows")
        rows.append(Row(cells[0], cells[1], words))
    return rows, problems


def rows(text: str) -> list[Row]:
    return [
        row
        for section in now_edit.now_of(text).sections
        if section.heading.lower() == "lemons"
        for row in parse(section.body)[0]
    ]


def render(listed: abc.Iterable[Row]) -> list[str]:
    lines = [
        f"| {row.lemon} | {row.purpose.replace('|', chr(92) + '|')} | {', '.join(row.watch)} |"
        for row in listed
    ]
    return ["| Lemon | Purpose | Watch |", "|---|---|---|", *lines] if lines else []


def _editable(text: str) -> list[Row]:
    problems = [
        problem
        for section in now_edit.now_of(text).sections
        if section.heading.lower() == "lemons"
        for problem in parse(section.body)[1]
    ]
    if problems:
        raise ValueError("Cannot rewrite ### Lemons: " + "; ".join(problems))

    return rows(text)


def checked_watch(watch: abc.Iterable[str]) -> tuple[str, ...]:
    words, problem = _words(",".join(watch))
    if problem:
        raise ValueError(problem)

    return words


def add(text: str, lemon: str, purpose: str, watch: abc.Iterable[str] = ()) -> str:
    """*text* with a row for *lemon*, replacing its row if it has one."""
    listed = _editable(text)
    at = next((i for i, row in enumerate(listed) if row.lemon == lemon), len(listed))
    listed[at : at + 1] = [Row(lemon, purpose, checked_watch(watch))]
    return now_edit.with_section(text, "Lemons", lambda body: render(listed))


def set_row(text: str, lemon: str, purpose: str | None, watch: abc.Iterable[str] | None) -> str:
    """*text* with *lemon*'s row changed; None keeps a cell as it was."""
    listed = _editable(text)
    at = next((i for i, row in enumerate(listed) if row.lemon == lemon), None)
    if at is None:
        raise ValueError(f"No row in ### Lemons for {lemon}")

    old = listed[at]
    listed[at] = Row(
        lemon,
        old.purpose if purpose is None else purpose,
        old.watch if watch is None else checked_watch(watch),
    )
    return now_edit.with_section(text, "Lemons", lambda body: render(listed))


def remove(text: str, lemon: str) -> str:
    listed = _editable(text)
    if not any(row.lemon == lemon for row in listed):
        raise ValueError(f"No row in ### Lemons for {lemon}")

    return now_edit.with_section(
        text, "Lemons", lambda body: render(row for row in listed if row.lemon != lemon)
    )
