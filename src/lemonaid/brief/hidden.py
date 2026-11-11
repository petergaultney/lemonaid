"""The `Hidden: yes` header line: a lemon the inbox leaves out of its default list."""

from . import flags


def is_hidden(text: str) -> bool:
    return flags.is_on(text, "Hidden")


def with_hidden(text: str, hidden: bool) -> str:
    """*text* with the header's `Hidden:` line set to `yes`, or removed."""
    return flags.with_flag(text, "Hidden", hidden)
