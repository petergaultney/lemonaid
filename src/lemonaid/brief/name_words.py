"""Words a lead suggests for its children's names, and the names they make.

A name is a five-letter word and a three-letter word, title-cased: `AuditInk`. The
words need not be WordyBin's. A lead lists them, best first, on a `Name words:`
line in its brief's header, or a caller passes them as `--name-words`.
"""

import dataclasses
import random
import re
from collections import abc

import wordybin

_NAME = re.compile(r"(?P<five>[A-Za-z]{5})(?P<three>[A-Za-z]{3})")
_WORD = re.compile(r"[A-Za-z]{5}|[A-Za-z]{3}")
_LINE = re.compile(r"Name words:(?P<words>.*)", re.IGNORECASE)
_SECTION = re.compile(r"#{1,2}\s")


@dataclasses.dataclass(frozen=True)
class Words:
    fives: tuple[str, ...] = ()
    threes: tuple[str, ...] = ()
    malformed: tuple[str, ...] = ()  # neither five nor three ASCII letters


NONE = Words()


def name(five: str, three: str) -> str:
    return five.title() + three.title()


def shaped(text: str) -> str:
    """*text* as a five-plus-three name (`auditINK` -> `AuditInk`), or "" if it isn't one."""
    match = _NAME.fullmatch(text)
    return name(match["five"], match["three"]) if match else ""


def parse(text: str) -> Words:
    """The words in *text*, separated by commas or spaces, in order and without repeats."""
    words = list(dict.fromkeys(w.lower() for w in re.split(r"[\s,]+", text) if w))
    return Words(
        fives=tuple(w for w in words if _WORD.fullmatch(w) and len(w) == 5),
        threes=tuple(w for w in words if _WORD.fullmatch(w) and len(w) == 3),
        malformed=tuple(w for w in words if not _WORD.fullmatch(w)),
    )


def read(text: str) -> Words | None:
    """The words on the `Name words:` line in *text*'s header, or None when it has none."""
    for line in text.splitlines():
        if _SECTION.match(line) and not line.startswith("# "):
            return None

        if match := _LINE.fullmatch(line.rstrip()):
            return parse(match["words"])

    return None


def problems(text: str) -> list[str]:
    """What `brief check` reports about *text*'s `Name words:` line."""
    words = read(text)
    if words is None or not words.malformed:
        return []

    return [f"`Name words:` {', '.join(words.malformed)} is not five or three letters"]


def _wordybin_fives() -> list[str]:
    return [wordybin.encode(bytes([i >> 1, (i & 1) << 7]))[:5].lower() for i in range(512)]


def _wordybin_threes() -> list[str]:
    return [wordybin.encode(bytes([0, i]))[5:].lower() for i in range(128)]


def names(words: Words, rng: random.Random) -> abc.Iterator[str]:
    """Every name *words* make, best first; a missing length is filled from WordyBin's words.

    Best first means the lowest sum of the two words' places in their lists, the
    five-letter word's place breaking ties.
    """
    if not words.fives and not words.threes:
        return

    fives = list(words.fives) or rng.sample(_wordybin_fives(), 512)
    threes = list(words.threes) or rng.sample(_wordybin_threes(), 128)
    ranked = sorted(
        ((i, j) for i in range(len(fives)) for j in range(len(threes))),
        key=lambda ij: (ij[0] + ij[1], ij[0]),
    )
    yield from (name(fives[i], threes[j]) for i, j in ranked)
