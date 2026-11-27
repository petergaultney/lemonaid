"""A plugin's answer to `poll`: records, each a line `<record> <value>` followed by its
field lines (docs/source-plugins.md). Lines lemonaid doesn't know are ignored."""

import contextlib
import typing as ty
from collections import abc


class Said(ty.NamedTuple):
    text: str
    label: str = ""
    count: int = 1


class Answer(ty.NamedTuple):
    cursor: str | None = None  # None: keep the cursor lemonaid has
    wake: Said | None = None
    end: Said | None = None
    problem: Said | None = None
    every: float | None = None  # None: poll again only when the plugin says `ready`


def _said(record: str, value: str, fields: abc.Sequence[tuple[str, str]]) -> Said:
    texts = [v for name, v in fields if name == "text"]
    label = next((v for name, v in fields if name == "label"), "")
    count = next((v for name, v in fields if name == "count"), "1")
    text = "\n".join(texts) if record == "wake" else value
    return Said(text, label, int(count) if count.isdigit() else 1)


def parse(text: str) -> Answer:
    records: list[tuple[str, str, list[tuple[str, str]]]] = []
    for line in text.splitlines():
        name, _, value = line.partition(" ")
        if name in ("wake", "end", "problem", "cursor", "every"):
            records.append((name, value, []))
        elif records:
            records[-1][2].append((name, value))
    found: dict[str, ty.Any] = {}
    for name, value, fields in records:
        if name == "cursor":
            found["cursor"] = value
        elif name == "every":
            with contextlib.suppress(ValueError):
                found["every"] = max(1.0, float(value))
        else:
            found[name] = _said(name, value, fields)
    return Answer(**found)
