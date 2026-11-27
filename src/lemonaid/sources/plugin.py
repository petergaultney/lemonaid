"""A configured watch source, and the `[[watch.sources]]` entries that name them."""

import dataclasses
import json
import re
import sys
import typing as ty
from collections import abc

from ..plugins import command

DEFAULT_ENTRIES: tuple[dict[str, str], ...] = ({"name": "slack", "command": "lemonaid-slack"},)
_NAME = re.compile(r"[a-z][a-z0-9-]*")


@dataclasses.dataclass(frozen=True)
class Source:
    plugin: command.Plugin
    table: str = "{}"  # the config file's top-level table named for it, as JSON

    @property
    def name(self) -> str:
        return self.plugin.name


def _table(tables: dict, name: str) -> str:
    found = tables.get(name, {})
    if not isinstance(found, dict):
        print(f"Warning: [{name}] must be a table", file=sys.stderr)
        return "{}"

    return json.dumps(found, default=str)


def parse(entries: object, tables: dict, taken: frozenset[str]) -> tuple[Source, ...]:
    """Sources in their configured order. *tables* is the whole config file; *taken* are the
    names lemonaid's own `watch` kinds use."""

    def bad_name(name: str) -> str:
        if _NAME.fullmatch(name) and name not in taken:
            return ""

        return (
            "must be lowercase letters, digits and dashes, and not a kind lemonaid watches itself"
        )

    return tuple(
        Source(found, _table(tables, found.name))
        for found in command.parse(entries, "watch.sources", DEFAULT_ENTRIES, bad_name)
    )


def defaults() -> tuple[Source, ...]:
    return parse(list(DEFAULT_ENTRIES), {}, frozenset())


class Words(ty.NamedTuple):
    args: tuple[str, ...]  # what the plugin is given
    me: str = ""
    once: bool = False


def words(after_name: abc.Sequence[str]) -> Words:
    """Split the words after `lemonaid watch <source>` into lemonaid's own options and the
    plugin's arguments."""
    args: list[str] = []
    me, once = "", False
    rest = iter(after_name)
    for word in rest:
        if word == "--me":
            me = next(rest, "")
        elif word.startswith("--me="):
            me = word.removeprefix("--me=")
        elif word == "--once":
            once = True
        else:
            args.append(word)
    return Words(tuple(args), me, once)


def named(sources: abc.Iterable[Source], name: str) -> Source | None:
    return next((s for s in sources if s.name == name), None)
