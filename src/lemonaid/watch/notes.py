"""Event notes: `~/.lemons/event-notes/<kind>.md`, appended to each event of that kind.

A note is static text, written by the user. It may hold harness sections, as a skill
overlay can. Nothing here can stop a delivery: a note that can't be read is logged and left
out.
"""

import pathlib
import typing as ty
from collections import abc

from ..home import layout
from ..log import get_logger
from ..skills import compose
from . import kinds

_log = get_logger("watch.notes")

MAX_CHARS = 2000
HEADING = "Your notes for these events:"

Reader = abc.Callable[[], abc.Mapping[str, str]]  # the notes as of now, read at delivery


class Loaded(ty.NamedTuple):
    notes: dict[str, str]  # kind to its text, rendered for one harness
    problems: list[str]


def default_dir() -> pathlib.Path:
    return layout.lemons_dir() / "event-notes"


def _read(path: pathlib.Path, harness: str) -> tuple[str, str]:
    """(text, problem) for one note file."""
    try:
        text = compose.for_harness(path.read_text(), harness).strip()
    except (OSError, UnicodeDecodeError) as error:
        return "", f"{path}: cannot read it ({error})"
    except compose.Problem as error:
        return "", f"{path}: {error}"

    if len(text) > MAX_CHARS:
        return text[:MAX_CHARS] + " ...", f"{path}: longer than {MAX_CHARS} characters; cut"

    return text, ""


def load(directory: pathlib.Path, harness: str) -> Loaded:
    """Every note in *directory* for *harness*, and what is wrong with any file there."""
    notes: dict[str, str] = {}
    problems: list[str] = []
    try:
        paths = sorted(p for p in directory.iterdir() if p.suffix == ".md")
    except FileNotFoundError:
        return Loaded(notes, problems)
    except OSError as error:
        problems.append(f"{directory}: cannot list it ({error})")
        paths = []

    for path in paths:
        if path.stem not in kinds.KINDS:
            problems.append(
                f"{path}: {path.stem!r} is not an event kind; see `lemonaid watch notes list`"
            )
            continue

        text, problem = _read(path, harness)
        if problem:
            problems.append(problem)
        if text:
            notes[path.stem] = text
    for problem in problems:
        _log.warning("%s", problem)
    return Loaded(notes, problems)


def reader(directory: pathlib.Path, harness: str) -> Reader:
    return lambda: load(directory, harness).notes


def none() -> abc.Mapping[str, str]:
    return {}


def appendix(present: abc.Iterable[str], notes: abc.Mapping[str, str]) -> str:
    """The notes for the kinds *present*, each once, or "" when none has one."""
    found = [kind for kind in dict.fromkeys(present) if kind in notes]
    if not found:
        return ""

    return "\n".join(
        [HEADING, *(f"- {kind}: " + notes[kind].replace("\n", "\n  ") for kind in found)]
    )
