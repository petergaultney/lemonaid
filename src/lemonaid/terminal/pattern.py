"""The regex a terminal uses to find a `.md` path under a vault root in its scrollback.

WezTerm compiles it with Rust's `regex` crate and iTerm2 with ICU, so it keeps to
what both accept: no lookaround, and escapes only on metacharacters. The roots are
literal prefixes, which is what lets a match run across the spaces in a folder name.
"""

from collections import abc
from pathlib import Path

from .. import obsidian

_META = frozenset("\\.^$*+?()[]{}|")
_CLASS_META = frozenset("\\[]^-&~")


def _escaped(text: str) -> str:
    return "".join(f"\\{char}" if char in _META else char for char in text)


def _class_escaped(chars: str) -> str:
    return "".join(f"\\{char}" if char in _CLASS_META else char for char in chars)


def vault_path_regex(roots: abc.Iterable[Path], excluded: str = "") -> str:
    """Matches a path to a `.md` file under one of *roots*, written from `~` or in full.

    The part after the root never contains a character in *excluded*.
    """
    spelled = sorted({s for root in roots for s in obsidian.spellings(root)}, key=len, reverse=True)
    return (
        "(?:"
        + "|".join(map(_escaped, spelled))
        + f")/[^\\n<>{_class_escaped('`[]' + excluded)}]*?\\.md\\b"
    )
