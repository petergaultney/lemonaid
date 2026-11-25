"""Which packages a lemon gets at session start, from each package's `package-for`.

A package is for a lemon when any item of its `package-for` matches, and an item
matches when all of its keys do:

- `cwd`: a glob on the session's working directory.
- `brief`: true for a lemon with an attached brief, false for one without.
- `brief-text`: a regex searched in the attached brief.
- `file`: a file name in the working directory or a folder above it.
- `branch: not-default`: `[docs] default-branch-check` fails in the working directory.
- `group`: the lemon is in that lemonaid group.
- `under`: the lemon descends from that Lemon-ID (or its name half) through parent links.
- `not`: an item that must not match.

`{}` matches every lemon. An unknown key matches no lemon, and is logged. A `load-when`
item takes the same keys, which limit its trigger to the lemons they match.
"""

import re
import subprocess
from collections import abc
from dataclasses import dataclass
from pathlib import Path

from .. import brief, groups, lineage
from ..hooks import session_brief
from ..inbox import db
from ..log import get_logger
from . import frontmatter, triggers

_log = get_logger("docs.lemons")

SCOPES = ("group", "under")  # the keys that name a group's or a lead's lemons


@dataclass(frozen=True)
class Lemon:
    cwd: Path
    brief: str = ""  # the attached brief's text; "" without one
    on_default_branch: bool | None = None  # None when unknown
    groups: tuple[str, ...] = ()
    ancestors: tuple[str, ...] = ()  # Lemon-IDs: its parent, that one's parent, and so on


def attached_brief(harness: str, session: str) -> str:
    """The text of the brief attached to *session*; "" without one."""
    path = session_brief.attached({"session_id": session}, harness)
    try:
        return path.read_text() if path else ""
    except OSError as e:
        _log.warning("could not read brief %s: %s", path, e)
        return ""


def kin(lemon_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """*lemon_id*'s groups and ancestors; empty without one."""
    if not lemon_id:
        return (), ()

    with db.connect() as conn:
        return groups.store.names_of(conn, lemon_id), tuple(lineage.links.ancestors(conn, lemon_id))


def lemon_id(brief_text: str) -> str:
    try:
        return brief.identity.read(brief_text) if brief_text else ""
    except ValueError as e:
        _log.warning("no Lemon-ID in the attached brief: %s", e)
        return ""


def on_default_branch(check: str, cwd: Path) -> bool | None:
    """Whether the shell command *check* succeeds in *cwd*; None without one, or when it
    can't run."""
    if not check:
        return None

    try:
        return (
            subprocess.run(["sh", "-c", check], cwd=cwd, capture_output=True, timeout=5).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("default-branch check in %s: %s", cwd, e)
        return None


def _searched(pattern: object, text: str) -> bool:
    try:
        return isinstance(pattern, str) and re.search(pattern, text, re.MULTILINE) is not None
    except re.error as e:
        _log.warning("brief-text %r: %s", pattern, e)
        return False


def _matches(key: str, value: object, lemon: Lemon) -> bool:
    if key == "cwd":
        return isinstance(value, str) and triggers.glob(value, lemon.cwd)
    if key == "brief":
        return value is bool(lemon.brief)
    if key == "brief-text":
        return bool(lemon.brief) and _searched(value, lemon.brief)
    if key == "file":
        return isinstance(value, str) and any(
            (d / value).exists() for d in (lemon.cwd, *lemon.cwd.parents)
        )
    if key == "branch":
        return value == "not-default" and lemon.on_default_branch is False
    if key == "group":
        return isinstance(value, str) and value in lemon.groups
    if key == "under":
        return isinstance(value, str) and any(
            value in (a, brief.identity.wordybin(a)) for a in lemon.ancestors
        )
    if key == "not":
        return isinstance(value, dict) and not applies(value, lemon)

    _log.warning("unknown package-for key %r", key)
    return False


def applies(item: abc.Mapping, lemon: Lemon) -> bool:
    return all(_matches(str(key), value, lemon) for key, value in item.items())


def scoped(item: abc.Mapping) -> bool:
    """Whether *item* names a group's or a lead's lemons, which classic lemons get too."""
    return any(key in item for key in SCOPES)


def packages(
    docs: abc.Iterable[frontmatter.Doc], lemon: Lemon, scoped_only: bool = False
) -> list[str]:
    """The packages whose index doc in *docs* is for *lemon*, in index order; with
    *scoped_only*, only by an item that names a group or a lead."""
    return list(
        dict.fromkeys(
            frontmatter.package_name(doc)
            for doc in docs
            if any(
                applies(item, lemon) and (scoped(item) or not scoped_only) for item in doc.lemons
            )
        )
    )
