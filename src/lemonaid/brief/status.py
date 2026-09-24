"""What a place's brief says about where its lemon's work stands.

A brief is `.z/brief.md`, or `.z/brief-<name>.md` when several lemons share a
directory. Its `Status:` line and `## Now` section are the worker's running
account of progress; everything else is the task statement it started from.
"""

import dataclasses
import re
from collections import abc
from pathlib import Path

from . import store

_BRIEF_FILE = re.compile(r"brief(?:-(?P<name>.+))?\.md")
_STATUS = re.compile(r"status:\s*(?P<status>.*)", re.IGNORECASE)
_NOW_HEADING = re.compile(r"##\s+now\s*", re.IGNORECASE)
_SECTION_END = re.compile(r"#{1,2}\s")
_GENERIC_TITLE_PREFIX = re.compile(r"^brief:\s*", re.IGNORECASE)


@dataclasses.dataclass(frozen=True)
class Brief:
    path: Path
    name: str  # the <name> in brief-<name>.md; empty for brief.md
    mtime: float
    text: str


@dataclasses.dataclass(frozen=True)
class Parts:
    title: str
    status: str
    raw_status: str
    now: str
    rest: str


def notes_dir(start: Path, place: Path | None) -> Path | None:
    """The nearest `.z/` from `start` up to `place`, or `start/.z` if there is none.

    A session's recorded cwd can be a subdirectory of the place it works in. The
    search never leaves the place: a `.z/` above it, or a `start` outside it,
    belongs to some other work, and is None. Without a place, only `start/.z`.
    """
    if place is None:
        return start / ".z"

    if not start.resolve().is_relative_to(place.resolve()):
        return None

    start, place = start.resolve(), place.resolve()
    for directory in (start, *start.parents):
        if (directory / ".z").is_dir():
            return directory / ".z"
        if directory == place:
            break

    return start / ".z"


def load(path: Path) -> Brief:
    return Brief(path, path.stem, path.stat().st_mtime, path.read_text())


def find_briefs(notes: Path) -> list[Brief]:
    """Every brief in a `.z/` directory, newest first."""
    if not notes.is_dir():
        return []

    briefs = [
        Brief(path, match["name"] or "", path.stat().st_mtime, path.read_text())
        for path in notes.iterdir()
        if path.is_file() and (match := _BRIEF_FILE.fullmatch(path.name))
    ]
    return sorted(briefs, key=lambda b: b.mtime, reverse=True)


def pick(briefs: abc.Sequence[Brief], names: abc.Iterable[str]) -> list[Brief]:
    """The brief belonging to one of `names`, else all of them.

    Names are compared case-insensitively against the `<name>` in
    `brief-<name>.md`, in the order given.
    """
    by_name = {b.name.lower(): b for b in briefs if b.name}
    for name in names:
        if brief := by_name.get(name.lower()):
            return [brief]

    return list(briefs)


def split(text: str) -> Parts:
    title, status = "", ""
    now: list[str] = []
    rest: list[str] = []
    in_now = False
    for line in text.splitlines():
        if in_now and _SECTION_END.match(line):
            in_now = False

        if not title and line.startswith("# "):
            title = line[2:].strip()
        elif not status and (match := _STATUS.fullmatch(line.strip())):
            status = match["status"]
        elif line.startswith("Parent:"):
            rest.append(line)  # template metadata, whether it sits above Now or below
        elif _NOW_HEADING.fullmatch(line):
            in_now = True
        elif in_now:
            now.append(line)
        else:
            rest.append(line)

    state = status.split(maxsplit=1)[0] if status else ""
    state = state.lower() if state.lower() in store.STATES else ""

    return Parts(title, state, status, "\n".join(now).strip(), "\n".join(rest).strip())


def age(seconds: float) -> str:
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit} ago"

    return "just now"


def _display_title(title: str) -> str:
    """The task itself, without the template's generic label."""
    return _GENERIC_TITLE_PREFIX.sub("", title, count=1).strip()


def _render_brief(brief: Brief, now: float, full: bool) -> str:
    parts = split(brief.text)
    title = _display_title(parts.title) or brief.name or "Work status"
    return "\n\n".join(
        [
            f"## {title}",
            f"*updated {age(now - brief.mtime)}*",
            f"**Status:** {parts.status or parts.raw_status or '(no Status line)'}",
            *([f"## Now\n\n{parts.now}"] if parts.now else []),
            *(["---", parts.rest] if full and parts.rest else []),
        ]
    )


def _render_all(briefs: abc.Sequence[Brief], now: float) -> str:
    return "\n\n---\n\n".join(_render_brief(b, now, full=len(briefs) == 1) for b in briefs)


def render(
    attached: abc.Sequence[Path],
    dirs: abc.Sequence[Path],
    place: Path | None,
    names: abc.Sequence[str],
    now: float,
) -> str:
    """Markdown for where the work in a place stands.

    Briefs attached to the session's lemons come first, and when there are any,
    nothing else is read. Otherwise the first directory holding a brief is used.
    One brief is shown with its task statement below a rule, out of the way;
    when several could be the one, each shows only its Status and Now. Without a
    brief anywhere, the first `.z/state.md` (written by lemons before
    compaction) stands in.
    """
    if attached:
        present = [load(path) for path in attached if path.is_file()]
        if present:
            return _render_all(sorted(present, key=lambda b: b.mtime, reverse=True), now)

        missing = ", ".join(f"`{path}`" for path in attached)
        return f"## Work status\n\nThe attached brief {missing} does not exist."

    notes_dirs = [notes for d in dirs if (notes := notes_dir(d, place))]
    for notes in notes_dirs:
        if briefs := pick(find_briefs(notes), names):
            return _render_all(briefs, now)

    for state in (notes / "state.md" for notes in notes_dirs):
        if not state.is_file():
            continue

        return "\n\n".join(
            [
                "## Work status",
                f"*`.z/state.md`, updated {age(now - state.stat().st_mtime)}*",
                "---",
                state.read_text().strip(),
            ]
        )

    searched = ", ".join(f"`{notes}`" for notes in notes_dirs)
    return f"## Work status\n\nNothing in {searched} says where this work stands."
