"""What a plugin's `threads` operation prints, read into records.

Each line is a field name, a space, and its value. `thread <key>` starts a record that
the lines after it describe; `note` and `incomplete` describe the whole reading. Unknown
fields are skipped, so a plugin may print fields a later lemonaid will read.
"""

import dataclasses
from collections import abc

_GIST_LIMIT = 100


@dataclasses.dataclass(frozen=True)
class Thread:
    key: str
    last: str  # who wrote last; "" when the plugin doesn't know
    waiting: bool  # it waits on the reader named in the call
    text: str
    gist: str


@dataclasses.dataclass(frozen=True)
class Reading:
    threads: tuple[Thread, ...]
    notes: tuple[str, ...]  # shown ahead of this plugin's new threads, e.g. how to answer them
    complete: bool  # False: some threads may be missing, so none is taken as answered


def _thread(fields: abc.Mapping[str, list[str]], key: str) -> Thread:
    text = "\n".join(fields.get("text", []))
    gist = (fields.get("gist") or [" ".join(text.split())[:_GIST_LIMIT]])[0]
    return Thread(key, (fields.get("last") or [""])[0], "waiting" in fields, text, gist)


def parse(output: str) -> Reading:
    threads: list[Thread] = []
    notes: list[str] = []
    complete = True
    current: tuple[str, dict[str, list[str]]] | None = None
    for line in output.split("\n"):
        name, _, value = line.partition(" ")
        if name == "thread" and value:
            if current:
                threads.append(_thread(current[1], current[0]))
            current = value, {}
        elif name == "note":
            notes.append(value)
        elif name == "incomplete":
            complete = False
        elif current and name in ("last", "waiting", "gist", "text"):
            current[1].setdefault(name, []).append(value)
    if current:
        threads.append(_thread(current[1], current[0]))
    return Reading(tuple(threads), tuple(notes), complete)


FAILED = Reading((), (), False)
