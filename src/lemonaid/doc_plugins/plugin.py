"""The `[[watch.doc.plugins]]` entries that name the document plugins."""

from ..plugins import command
from ..plugins.command import Plugin

DEFAULT_ENTRIES: tuple[dict[str, str], ...] = (
    {"name": "relay-comments", "command": "lemonaid-relay-comments"},
)


def parse(entries: object) -> tuple[Plugin, ...]:
    return command.parse(entries, "watch.doc.plugins", DEFAULT_ENTRIES)


def defaults() -> tuple[Plugin, ...]:
    return parse(list(DEFAULT_ENTRIES))
