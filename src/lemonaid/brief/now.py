"""The labelled parts of a brief's `## Now` section.

A worker writes each part either as a sub-heading (`### Needs Peter`) with
anything under it, or as a top-level bullet (`- Needs Peter: ...`) with its
own indented sub-bullets. Lines under no known label are kept, in order.

The request for a person is `Needs` followed by at most one word naming them
(`Needs`, `Needs Peter`, `Needs you`), kept as written.
"""

import dataclasses
import re
import textwrap
from collections import abc

_LABELS = {
    "waiting on": "waiting_on",
    "next": "next",
    "done": "done",
}
_HEADING = re.compile(r"#{3,6}\s+(?P<label>.+?)\s*:?\s*#*\s*")
_LABELLED_BULLET = re.compile(r"[-*+]\s+(?P<label>[^:]+?)\s*:\s*(?P<rest>.*)")
_NEEDS = re.compile(r"needs(?:\s+\S+)?", re.IGNORECASE)
_TOP_LEVEL_BULLET = re.compile(r"[-*+]\s")
_EMPTY = {"", "nothing", "none", "n/a", "-"}


@dataclasses.dataclass(frozen=True)
class Now:
    needs: str = ""
    needs_label: str = "Needs"
    waiting_on: str = ""
    next: str = ""
    done: str = ""
    other: str = ""


def _field(label: str) -> str:
    plain = label.strip().strip("*_").strip()
    return "needs" if _NEEDS.fullmatch(plain) else _LABELS.get(plain.lower(), "")


def _cleaned(lines: abc.Sequence[str]) -> str:
    """A part's Markdown, or "" when it only says there is nothing."""
    first, *rest = lines or [""]
    text = "\n".join([first.strip(), textwrap.dedent("\n".join(rest))]).strip()
    return "" if text.rstrip(".").strip().lower() in _EMPTY else text


def parse(now: str) -> Now:
    parts: dict[str, list[str]] = {field: [] for field in ("needs", *_LABELS.values(), "other")}
    needs_label = "Needs"
    current = "other"
    from_bullet = False
    for line in now.splitlines():
        if heading := _HEADING.fullmatch(line):
            current = _field(heading["label"]) or "other"
            from_bullet = False
            if current == "needs":
                needs_label = heading["label"].strip("*_").strip()
            if current == "other":
                parts["other"].append(line)
            continue

        bullet = _LABELLED_BULLET.fullmatch(line)
        if bullet and (field := _field(bullet["label"])):
            current, from_bullet = field, True
            parts[field].append(bullet["rest"])
            if field == "needs":
                needs_label = bullet["label"].strip("*_").strip()
            continue

        if from_bullet and _TOP_LEVEL_BULLET.match(line):
            current, from_bullet = "other", False

        parts[current].append(line)

    cleaned = {field: _cleaned(lines) for field, lines in parts.items()}
    return Now(needs_label=needs_label if cleaned["needs"] else "Needs", **cleaned)


def summary(text: str) -> str:
    """One line for a part: its lead line, or its first item and how many more there are."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    if not _TOP_LEVEL_BULLET.match(lines[0]):
        return lines[0].strip()

    items = [line[2:].strip() for line in lines if _TOP_LEVEL_BULLET.match(line)]
    return items[0] if len(items) == 1 else f"{items[0]} (+{len(items) - 1} more)"
