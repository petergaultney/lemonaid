"""One line of a lemon's conversation, the same whichever harness recorded it."""

import json
import typing as ty
from collections import abc
from pathlib import Path

USER = "user"  # typed by the lemon's user
LEMON = "lemon"
TOOL = "tool"  # a tool the lemon ran, folded to one line
OTHER = "other"  # input that is not the user's: mail, events, other sessions
FAILED = "failed"  # a turn that ended in an error, with why

_TAIL = 2 * 1024 * 1024


class Entry(ty.NamedTuple):
    role: str
    text: str
    at: str  # ISO 8601 as the harness wrote it, or ""
    sender: str = ""  # who sent OTHER input, when the harness says
    files: tuple[tuple[str, int], ...] = ()  # (name, bytes) of each file sent with it


def tail_records(path: Path) -> abc.Iterator[dict]:
    """The JSON records in the last part of a JSONL file, oldest first."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            start = max(0, f.tell() - _TAIL)
            f.seek(start)
            lines = f.read().splitlines()
    except OSError:
        return

    for line in lines[1 if start else 0 :]:  # a tail's first line may be cut mid-record
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record


def newest(entries: abc.Iterable[Entry], limit: int) -> list[Entry]:
    """The entries back to the *limit*th newest that isn't a tool call. A page folds each run of
    tool calls to one line, so they don't count toward *limit*."""
    found = list(entries)
    said = [at for at, each in enumerate(found) if each.role != TOOL]
    return found[said[-limit] :] if limit > 0 and len(said) >= limit else found


def one_line(text: str, width: int = 160) -> str:
    first = " ".join(text.split())
    return first if len(first) <= width else first[: width - 3] + "..."
