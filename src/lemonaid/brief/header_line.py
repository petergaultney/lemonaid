"""A `Name: value` line in a brief's header, above its first `## ` heading and outside code fences."""

import re

_FENCE = re.compile(r"(```|~~~)")


def read(text: str, name: str) -> str | None:
    """The value on *text*'s header `<name>:` line, or None without one."""
    prefix = f"{name}:"
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        elif line.startswith("## "):
            return None
        elif not in_fence and line.startswith(prefix) and line[len(prefix) :].strip():
            return line[len(prefix) :].strip()

    return None
