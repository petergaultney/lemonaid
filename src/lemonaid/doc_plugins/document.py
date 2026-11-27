"""A document as the configured plugins read it: its body, and its comment threads."""

import dataclasses
from collections import abc
from pathlib import Path

from ..plugins.command import Plugins
from . import protocol, run


@dataclasses.dataclass(frozen=True)
class PluginReading:
    plugin: str
    reading: protocol.Reading


def body(plugins: Plugins, path: Path, text: str) -> str | None:
    """*text* with every plugin's comments removed, each plugin reading what the one before it
    left; None when one failed, since a body that still holds comments would read as an edit."""
    for plugin in plugins:
        found = run.call(plugin, "body", path, text)
        if found is None:
            return None

        text = found
    return text


def threads(
    plugins: Plugins, path: Path, text: str, names: abc.Iterable[str]
) -> list[PluginReading]:
    """Each plugin's threads in *text*, as the reader signing with any of *names* sees them.
    Every plugin reads the same text; a plugin that failed reads as incomplete."""
    args = sorted(names)
    return [
        PluginReading(
            plugin.name,
            protocol.FAILED
            if (output := run.call(plugin, "threads", path, text, args)) is None
            else protocol.parse(output),
        )
        for plugin in plugins
    ]


def last_authors(plugins: Plugins, path: Path, text: str) -> frozenset[str]:
    """Who wrote last in each thread, whichever plugin found it."""
    return frozenset(
        t.last
        for found in threads(plugins, path, text, ())
        for t in found.reading.threads
        if t.last
    )
