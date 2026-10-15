"""The `Hidden: yes` header line: a lemon the inbox leaves out of its default list."""

import re

from . import store

_LINE = re.compile(r"hidden:\s*(.*)", re.IGNORECASE)
_ON = ("yes", "true")


def is_hidden(text: str) -> bool:
    lines = text.splitlines()
    return any(
        (found := _LINE.fullmatch(line.strip())) and found.group(1).strip().lower() in _ON
        for line in lines[: store.header_end(lines)]
    )


def with_hidden(text: str, hidden: bool) -> str:
    """*text* with the header's `Hidden:` line set to `yes`, or removed."""
    lines = text.splitlines()
    end = store.header_end(lines)
    kept = []
    for i, line in enumerate(lines):
        if i < end and _LINE.fullmatch(line.strip()):
            continue

        if i < end and i and not line.strip() and _LINE.fullmatch(lines[i - 1].strip()):
            continue

        kept.append(line)

    if not hidden:
        return "\n".join(kept).rstrip("\n") + "\n"

    at = 1 if kept and kept[0].startswith("# ") else 0
    return "\n".join([*kept[:at], "", "Hidden: yes", *kept[at:]]).lstrip("\n").rstrip("\n") + "\n"
