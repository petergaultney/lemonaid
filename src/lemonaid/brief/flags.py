"""Yes-or-absent header lines such as `Hidden: yes`, which a brief's frontmatter keeps as `true`."""

import re

from . import frontmatter, store

_ON = ("yes", "true")


def _line(label: str) -> re.Pattern[str]:
    return re.compile(rf"{re.escape(label)}:\s*(.*)", re.IGNORECASE)


def is_on(text: str, label: str) -> bool:
    line = _line(label)
    lines = frontmatter.legacy(text).splitlines()
    return any(
        (found := line.fullmatch(each.strip())) and found.group(1).strip().lower() in _ON
        for each in lines[: store.header_end(lines)]
    )


def with_flag(text: str, label: str, on: bool) -> str:
    """*text* with the header's *label* line set to `yes`, or removed."""
    line = _line(label)
    lines = text.splitlines()
    end = store.header_end(lines)
    kept = []
    for i, each in enumerate(lines):
        if i < end and line.fullmatch(each.strip()):
            continue

        if i < end and i and not each.strip() and line.fullmatch(lines[i - 1].strip()):
            continue

        kept.append(each)

    if not on:
        return "\n".join(kept).rstrip("\n") + "\n"

    at = 1 if kept and kept[0].startswith("# ") else 0
    return "\n".join([*kept[:at], "", f"{label}: yes", *kept[at:]]).lstrip("\n").rstrip("\n") + "\n"
