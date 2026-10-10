"""Brief files in `~/.lemons/brief/`: naming, creating, and the two edits a worker makes.

Everything but the `Status:` line and the `## Now` section is left as written,
so sections other tools add (such as `## Waiters`) survive every edit here.

Only files inside `briefs_dir()` count as briefs. Lemonaid writes to them for
sandboxed lemons (a Codex exec-policy rule runs `lemonaid brief ...` outside
the sandbox), so the folder is the boundary of what those commands can touch.
Until `lemonaid home migrate` has run, that folder is `~/.brief-lemons/`.
"""

import datetime
import os
import re
import tempfile
from collections import abc
from pathlib import Path

from .. import home
from . import names

# The statuses a lemon sets. Without one, the inbox shows the lemon's own state
# (active, idle, deaf or dead); see docs/brief-status.md.
STATES = ("running", "done", "blocked", "merge", "approve", "alert", "review")
# Statuses lemons once set by hand, now read as no status.
RETIRED = ("working", "waiting")
CLEAR = "clear"

_EDIT_ATTEMPTS = 5

_STATUS_LINE = re.compile(r"status:\s*.*", re.IGNORECASE)
_NOW_HEADING = re.compile(r"##\s+now\s*", re.IGNORECASE)
_SECTION = re.compile(r"#{1,2}\s")

_TEMPLATE = """\
# {title}

Brief-ID: {lemon_id}

## Now
- Starting.

## Goal

## Context

## Limits

## Output
"""


def briefs_dir() -> Path:
    override = os.environ.get("LEMONAID_BRIEFS_DIR")
    return Path(override) if override else home.layout.briefs_dir()


def resolve(name: str) -> Path:
    """A brief named on the command line: relative names are inside `briefs_dir()`."""
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = briefs_dir() / path
        if not path.suffix:
            path = path.with_suffix(".md")

    return path.resolve()


def outside_error(path: Path) -> str:
    """Why *path* can't be a brief, or "" if its real path is inside `briefs_dir()`."""
    if paused := home.layout.paused():
        return paused

    if path.resolve().is_relative_to(briefs_dir().resolve()):
        return ""

    return f"{path} is not inside {briefs_dir()}; briefs live there"


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-") or "brief"


def lemon_id_slug(path: Path) -> str:
    """The readable part of a Lemon-ID for the brief at *path*, before its WordyBin."""
    readable = slug(re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem))
    if len(readable) <= 40:
        return readable

    prefix = readable[:40]
    return (prefix.rsplit("-", 1)[0] if "-" in prefix else prefix).rstrip("-") or "brief"


def new_lemon_id(path: Path) -> str:
    """Give a brief a short name plus a new name from `names`: by default a random WordyBin."""
    return f"{lemon_id_slug(path)}.{names.new()}"


def create_named(name: str, today: datetime.date, text: abc.Callable[[Path], str]) -> Path:
    """A new brief `<date>-<name>.md` holding *text* of its path. Never overwrites."""
    with home.guard.operation():
        directory = briefs_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{today.isoformat()}-{name}.md"
        content = text(path)  # a failure here leaves no empty file
        with path.open("x") as f:
            f.write(content)

    return path.resolve()


def create(title: str, today: datetime.date) -> Path:
    """A new brief from the template, named `<date>-<slug>.md`. Never overwrites."""
    return create_named(
        slug(title),
        today,
        lambda path: _TEMPLATE.format(title=title.strip(), lemon_id=new_lemon_id(path)),
    )


class ChangedUnderneath(Exception):
    pass


def _replace(path: Path, text: str) -> None:
    """Write *path* whole, so a reader never sees half of it."""
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(temp, path.stat().st_mode & 0o7777)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def edit(path: Path, change: abc.Callable[[str], str]) -> None:
    """Apply *change* to the file's text, re-applying it if the file is saved meanwhile.

    The brief is often open in an editor. Reading it again just before the
    write narrows the window in which someone else's save is lost to the
    rename itself; the edits here touch one section, so re-applying them to
    the newer text keeps both.
    """
    with home.guard.operation():
        for _ in range(_EDIT_ATTEMPTS):
            before = path.read_text()
            after = change(before)
            if path.read_text() == before:
                _replace(path, after)
                return

    raise ChangedUnderneath(f"{path} kept changing while it was being edited; try again")


def _without_status(lines: list[str], i: int) -> str:
    """*lines* less the `Status:` line at *i* and the blank line that set it apart."""
    end = i + 1 if i + 1 < len(lines) and lines[i + 1].strip() else i + 2
    return "\n".join([*lines[:i], *lines[end:]]).rstrip("\n") + "\n"


def with_status(text: str, state: str) -> str:
    """Set the first `Status:` line without changing `## Now`; `CLEAR` removes it."""
    line = f"Status: {state}"
    lines = text.splitlines()
    for i, existing in enumerate(lines):
        if _STATUS_LINE.fullmatch(existing.strip()):
            if state == CLEAR:
                return _without_status(lines, i)

            return "\n".join([*lines[:i], line, *lines[i + 1 :]]) + "\n"

    if state == CLEAR:
        return text

    title_end = 1 if lines and lines[0].startswith("# ") else 0
    return "\n".join([*lines[:title_end], "", line, *lines[title_end:]]).lstrip("\n") + "\n"


def with_now(text: str, now: str) -> str:
    """*text* with its `## Now` section's body replaced.

    A missing one goes after the header lines (`Status:`, `Parent:`, `Area:`), so
    they stay outside it.
    """
    lines = text.splitlines()
    body = [*now.strip().splitlines(), ""]
    start = next((i for i, line in enumerate(lines) if _NOW_HEADING.fullmatch(line)), None)
    if start is None:
        status = next(
            (i + 1 for i, line in enumerate(lines) if _STATUS_LINE.fullmatch(line.strip())),
            1 if lines and lines[0].startswith("# ") else 0,
        )
        at = next((i for i in range(status, len(lines)) if _SECTION.match(lines[i])), len(lines))
        head = lines[:at]
        while head and not head[-1].strip():
            head.pop()
        return "\n".join([*head, "", "## Now", *body, *lines[at:]]).rstrip("\n") + "\n"

    end = next(
        (i for i in range(start + 1, len(lines)) if _SECTION.match(lines[i])),
        len(lines),
    )
    return "\n".join([*lines[: start + 1], *body, *lines[end:]]).rstrip("\n") + "\n"
