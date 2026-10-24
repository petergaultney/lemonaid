"""Short tree labels and their letters.

A tree is named by the words that tell it apart within its block: the group's own words and
words most of its trees share are dropped, so the trees of `oria-postgres` read `core`, `ops` and
`roles` rather than `tars/postgres-core`. Its letter comes from those words when it can.
"""

import re
from collections import abc

LEAD_LETTER = "l"
_WORD = re.compile(r"[a-z0-9]+")


_SHORTEST = 4  # letters a shortened label keeps at least


def words(name: str) -> list[str]:
    return _WORD.findall(name.lower())


def _leaf(key: str) -> str:
    return key.rstrip("/").rsplit("/", 1)[-1] or key


def labels(group: str, keys: abc.Sequence[str]) -> dict[str, str]:
    leaves = {key: _leaf(key) for key in keys}
    dropped = set(words(group))
    if len(keys) > 1:
        counts: dict[str, int] = {}
        for leaf in leaves.values():
            for word in set(words(leaf)):
                counts[word] = counts.get(word, 0) + 1
        dropped |= {word for word, count in counts.items() if count >= 2 and count * 2 > len(keys)}

    def short(key: str) -> str:
        kept = " ".join(word for word in words(leaves[key]) if word not in dropped)
        # Too short and it stops saying which tree it is: `oria-hq` would be `hq`, like HQ's own.
        return kept if len(kept) >= _SHORTEST else " ".join(words(leaves[key])) or key

    return {key: short(key) for key in keys}


def without_group(group: str, name: str) -> str:
    """*name* without the group's own words at its start, as `Oria chat error` in `oria` reads
    `chat error`; all of *name* when nothing else is left.
    """
    group_words = set(words(group))
    tokens = name.split()
    start = 0
    while start < len(tokens) and words(tokens[start]) and set(words(tokens[start])) <= group_words:
        start += 1
    return " ".join(tokens[start:]) or name


LETTERS = "abcdefghijklmnoprstuvwxyz"  # a tree's letter, never q, which quits; its capital opens its other lemons


def pick_letter(label: str, taken: abc.Container[str]) -> str:
    """The first free letter from *label*'s words' initials, then its other letters, then a-z;
    always lowercase, since a capital opens a tree's other lemons.
    """
    lowered = label.lower()
    initials = [word[0] for word in lowered.split()]
    for char in [*initials, *lowered, *LETTERS]:
        if char in LETTERS and char != LEAD_LETTER and char not in taken:
            return char
    return ""
