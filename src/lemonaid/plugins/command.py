"""A configured plugin: its name and the command that starts it."""

import dataclasses
import shlex
import sys
from collections import abc
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Plugin:
    name: str
    argv: tuple[str, ...]


Plugins = abc.Sequence[Plugin]


def argv(command: str) -> tuple[str, ...]:
    """*command* split as a shell would, without running one. A bare program installed in
    lemonaid's own environment is found there, so a waiter needs no PATH that includes it."""
    split = shlex.split(command)
    beside = Path(sys.executable).parent / split[0] if split and "/" not in split[0] else None
    return (str(beside), *split[1:]) if beside and beside.exists() else tuple(split)
