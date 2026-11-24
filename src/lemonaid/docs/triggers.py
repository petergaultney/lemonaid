"""Whether a doc's trigger matches what a lemon is doing.

A `command` regex is searched in each simple command of a shell line, split at `&&`,
`||`, `;`, `|` and newlines, after any leading `NAME=value` assignments, so
`^gh pr create` matches `cd repo && GH_HOST=x gh pr create`. The split ignores quoting;
a quoted separator splits too. A `prompt` regex is searched in the user's message.

An `edit` or `create` glob matches a written path: `*` and `?` within one folder, `**`
across folders. A glob starting with `/` or `~` matches from the root; any other matches
at any depth, so `*.py` matches every Python file.
"""

import functools
import os
import re
from collections import abc
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter

_SEPARATOR = re.compile(r"&&|\|\||[;|\n]")
_ASSIGNMENT = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+")
_GLOB_PART = re.compile(r"(\*\*/|\*\*|\*|\?)")
_GLOB = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}


@dataclass(frozen=True)
class Action:
    commands: tuple[str, ...] = ()
    written: tuple[Path, ...] = ()
    created: tuple[Path, ...] = ()
    prompt: str = ""


def _simple(commands: abc.Iterable[str]) -> abc.Iterator[str]:
    for command in commands:
        for part in _SEPARATOR.split(command):
            yield _ASSIGNMENT.sub("", part.strip())


@functools.cache
def _glob_regex(pattern: str) -> re.Pattern[str]:
    anchored = os.path.expanduser(pattern)
    if not anchored.startswith("/"):
        anchored = f"**/{anchored}"
    return re.compile("".join(_GLOB.get(p, re.escape(p)) for p in _GLOB_PART.split(anchored)))


def glob(pattern: str, path: Path | str) -> bool:
    return _glob_regex(pattern).fullmatch(str(path)) is not None


def _searched(pattern: str, texts: abc.Iterable[str]) -> bool:
    try:
        return any(re.search(pattern, text) for text in texts)
    except re.error:
        return False  # the index logged it when it was built


def matches(trigger: frontmatter.Trigger, action: Action) -> bool:
    if trigger.kind == "command":
        return _searched(trigger.pattern, _simple(action.commands))
    if trigger.kind == "prompt":
        return _searched(trigger.pattern, [action.prompt] if action.prompt else [])

    paths = {"edit": action.written, "create": action.created}.get(trigger.kind, ())
    return any(glob(trigger.pattern, path) for path in paths)
