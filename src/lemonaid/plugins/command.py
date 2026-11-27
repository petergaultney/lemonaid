"""A configured plugin: its name and the command that starts it, and the config entries that
name them."""

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


def _entry(entry: object) -> tuple[str, str] | None:
    name = entry.get("name") if isinstance(entry, dict) else None
    run = entry.get("command") if isinstance(entry, dict) else None
    if isinstance(name, str) and name and isinstance(run, str) and run.strip():
        return name, run

    return None


def parse(
    entries: object,
    table: str,
    default: abc.Sequence[abc.Mapping[str, str]],
    bad_name: abc.Callable[[str], str] = lambda name: "",
) -> tuple[Plugin, ...]:
    """The `[[<table>]]` entries' plugins in their configured order; an entry without a name
    and a command, or whose name *bad_name* says why it can't have, is skipped with a warning.
    *entries* that are not a list give *default*."""
    if not isinstance(entries, list):
        section, _, key = table.rpartition(".")
        print(f"Warning: [{section}] {key} must be a list of tables", file=sys.stderr)
        return parse(list(default), table, default, bad_name)

    found: list[Plugin] = []
    for entry in entries:
        named = _entry(entry)
        if named is None:
            print(
                f"Warning: [[{table}]] {entry!r} needs a name and a command; ignored",
                file=sys.stderr,
            )
        elif why := bad_name(named[0]):
            print(f"Warning: [[{table}]] {named[0]!r} {why}; ignored", file=sys.stderr)
        elif any(p.name == named[0] for p in found):
            print(f"Warning: [[{table}]] {named[0]!r} is named twice", file=sys.stderr)
        else:
            found.append(Plugin(named[0], argv(named[1])))
    return tuple(found)
