"""A configured document plugin, and the `[[watch.doc.plugins]]` entries that name them."""

import sys

from ..plugins import command
from ..plugins.command import Plugin

DEFAULT_ENTRIES: tuple[dict[str, str], ...] = (
    {"name": "relay-comments", "command": "lemonaid-relay-comments"},
)


def parse(entries: object) -> tuple[Plugin, ...]:
    """Plugins in their configured order; an entry without a name and command is skipped."""
    if not isinstance(entries, list):
        print("Warning: [watch.doc] plugins must be a list of tables", file=sys.stderr)
        return parse(list(DEFAULT_ENTRIES))

    found: list[Plugin] = []
    for entry in entries:
        name = entry.get("name") if isinstance(entry, dict) else None
        entry_command = entry.get("command") if isinstance(entry, dict) else None
        if not (
            isinstance(name, str)
            and name
            and isinstance(entry_command, str)
            and entry_command.strip()
        ):
            print(
                f"Warning: [[watch.doc.plugins]] {entry!r} needs a name and a command; ignored",
                file=sys.stderr,
            )
        elif any(p.name == name for p in found):
            print(f"Warning: [[watch.doc.plugins]] {name!r} is named twice", file=sys.stderr)
        else:
            found.append(Plugin(name, command.argv(entry_command)))
    return tuple(found)


def defaults() -> tuple[Plugin, ...]:
    return parse(list(DEFAULT_ENTRIES))
