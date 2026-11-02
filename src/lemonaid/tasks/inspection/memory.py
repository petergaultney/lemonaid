"""What a long-running inspector remembers between passes, so the checker isn't asked about
a subject again until something it was shown changes or its findings come due.

A subject's input is fingerprinted without the pass's `now` and each fact's observation
time, so only a change in what lemonaid sees counts. Its findings hold until the earliest
`recheck` or `wait` time among them; findings with neither hold until the input changes.
"""

import hashlib
import math
import typing as ty
from collections import abc

from ..checker import checker_input, protocol
from ..checker.session import Ask

_OBSERVED_AT = 5  # a fact line's field, after the kind


class Memory(ty.NamedTuple):
    watches: dict[str, tuple[str, list[tuple[str, str]]]]  # subject -> describe input, watches
    judged: dict[str, tuple[str, float]]  # subject -> evaluate input, when its findings expire


def new() -> Memory:
    return Memory({}, {})


def fingerprint(text: str) -> str:
    kept = []
    for line in text.splitlines():
        fields = line.split("\t")
        if fields[:2] == ["context", "now"]:
            continue

        if fields[0] == "fact":
            del fields[_OBSERVED_AT]
        kept.append("\t".join(fields))
    return hashlib.sha256("\n".join(kept).encode()).hexdigest()


def _until(records: abc.Iterable[protocol.Record]) -> float:
    """Raises ProtocolError for a time that isn't RFC 3339, so the subject's checker run
    fails like any other malformed output."""
    times = [r[2] for r in records if r[0] == "recheck"] + [r[5] for r in records if r[0] == "wait"]
    try:
        return min((checker_input.timestamp(t).timestamp() for t in times), default=math.inf)
    except ValueError as error:
        raise protocol.ProtocolError(f"the checker gave a bad time: {error}") from None


def watches(
    memory: Memory,
    subject: str,
    text: str,
    ask: Ask,
    declare: abc.Callable[[Ask, str], list[tuple[str, str]]],
) -> list[tuple[str, str]]:
    """The watches *declare* gets from the checker for *text*, asked again only when the
    input changed."""
    key = fingerprint(text)
    held = memory.watches.get(subject)
    if held is not None and held[0] == key:
        return held[1]

    found = declare(ask, text)
    memory.watches[subject] = (key, found)
    return found


def unchanged(memory: Memory, subject: str, text: str, now: float) -> bool:
    held = memory.judged.get(subject)
    return held is not None and held[0] == fingerprint(text) and now < held[1]


def remember(
    memory: Memory, subject: str, text: str, records: abc.Iterable[protocol.Record]
) -> None:
    memory.judged[subject] = (fingerprint(text), _until(records))


def forget(memory: Memory, subject: str) -> None:
    memory.watches.pop(subject, None)
    memory.judged.pop(subject, None)
