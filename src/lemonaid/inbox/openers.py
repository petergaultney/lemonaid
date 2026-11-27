"""`[inbox.openers]`: commands a row's Enter may run, by name, for rows that name a file.

A row asks for one with metadata `{"opener": "<name>", "path": "<file>"}`; the command comes
from config and the row supplies only the path, which fills `{path}` in each argument. No
shell runs it. A missing or failed opener falls back to the row's `open_uri`, if it has one.
"""

import shlex
import subprocess
import sys
from collections import abc
from typing import Any

from ..log import get_logger

_log = get_logger("openers")

Openers = abc.Mapping[str, tuple[str, ...]]


def parse(data: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(data, dict):
        print("Warning: [inbox.openers] must be a table of commands", file=sys.stderr)
        return {}

    found = {}
    for name, command in data.items():
        if isinstance(command, str) and "{path}" in command and shlex.split(command):
            found[str(name)] = tuple(shlex.split(command))
        else:
            print(
                f"Warning: [inbox.openers] {name} must be a command that uses {{path}}; ignored",
                file=sys.stderr,
            )
    return found


def argv(openers: Openers, metadata: abc.Mapping[str, Any]) -> list[str] | None:
    """The command a row's metadata asks for, or None when it names no configured opener."""
    command = openers.get(str(metadata.get("opener") or ""))
    path = metadata.get("path")
    if command is None or not isinstance(path, str) or not path:
        return None

    return [arg.replace("{path}", path) for arg in command]


def run(openers: Openers, metadata: abc.Mapping[str, Any]) -> bool:
    found = argv(openers, metadata)
    if found is None:
        return False

    _log.info("opening with %s", found)
    try:
        return subprocess.run(found, check=False, capture_output=True).returncode == 0
    except OSError as e:
        _log.warning("opener %s failed: %s", found[0], e)
        return False
