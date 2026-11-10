"""What lemonaid asks of a front end: the terminal a lemon runs in.

An operation a front end can't do is None, and its caller says so rather than
guessing. A new front end fills in both records; nothing else learns its name.

The two records follow the import order: a `Terminal` only looks at terminals,
so `handlers`, which much of lemonaid imports, can use it. A `FrontEnd` also
starts harnesses, which needs `launch`, and `launch` imports `handlers`.
"""

import argparse
import dataclasses
import typing as ty
from collections import abc

from ..config import Config
from ..inbox import db

Metadata = dict[str, ty.Any]
Revive = abc.Callable[[db.Notification, Config, str], str]  # with the text to send; why not, or ""


@dataclasses.dataclass(frozen=True)
class Terminal:
    name: str  # as inbox rows record it in `switch_source`
    here: abc.Callable[[], bool]  # whether the caller runs in it
    show: abc.Callable[[Metadata, Config, abc.Callable[[str], None] | None], bool]
    """Bring a lemon to the front, resuming it if its pane is gone; a front end that
    resumes calls the callback with the new tty."""
    exists: abc.Callable[[str, str | None, float | None], bool | None]
    """Whether the pane on a tty (on an instance, recorded at a time) is still there;
    None when that can't be told."""
    lost: abc.Callable[[abc.Sequence[Metadata]], list[bool | None]] = lambda rows: (
        [None] * len(rows)
    )
    """For each recorded location, whether the terminal instance it was in has gone away
    (a server that died or was replaced), False if it still runs, None if that can't be told.
    A pane closed on a running instance is not lost."""


@dataclasses.dataclass(frozen=True)
class FrontEnd:
    terminal: Terminal
    open_beside: abc.Callable[[argparse.Namespace, Config], tuple[dict, str]]
    """`lemon start` with no target: the caller's neighbor, as (JSON result, error)."""
    start: Revive | None  # resume a lemon whose harness exited, where it was
    prompt: Revive | None  # type into a lemon idle at its prompt
