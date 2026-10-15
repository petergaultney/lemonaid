"""The regex a terminal uses to find a `.md` path under a vault root in its scrollback.

WezTerm compiles it with Rust's `regex` crate and iTerm2 with ICU, so it keeps to
what both accept: no lookaround, and escapes only on metacharacters. The roots are
literal prefixes, which is what lets a match run across the spaces in a folder name.
"""

from collections import abc
from pathlib import Path

from .. import obsidian

_META = frozenset("\\.^$*+?()[]{}|")
_TOKEN_START = "(?:^|[\\s(\\[{\"'`:<>|,])"
_CLASS_META = frozenset("\\[]^-&~")


def _escaped(text: str) -> str:
    return "".join(f"\\{char}" if char in _META else char for char in text)


def _class_escaped(chars: str) -> str:
    return "".join(f"\\{char}" if char in _CLASS_META else char for char in chars)


def vault_path_regex(
    roots: abc.Iterable[Path], excluded: str = "", spaced_folders: abc.Iterable[str] = ()
) -> str:
    """Matches a path to a `.md` file under one of *roots*, written from `~` or in full.

    It also matches a path written without a root: a run of non-space characters
    ending in `.md` (no `:`, so no URL), or one starting with a folder name from *spaced_folders*, which a
    plain run could not cover. Paths start a line or follow whitespace or an opening
    delimiter. Capture group 1 holds the path without that leading character, which
    the full match includes because Rust regex has no lookbehind. Nothing after a
    root or folder contains a character in *excluded*.
    """
    spelled = sorted({s for root in roots for s in obsidian.spellings(root)}, key=len, reverse=True)
    barred = _class_escaped("`[]" + excluded)
    token_barred = _class_escaped("`[]{}()\"'|," + excluded)
    tail = f"/[^\\n<>{barred}]*?\\.md\\b"
    folders = sorted(spaced_folders, key=len, reverse=True)
    paths = "|".join(
        [
            "(?:" + "|".join(map(_escaped, spelled)) + ")" + tail,
            *(["(?:" + "|".join(map(_escaped, folders)) + ")" + tail] if folders else []),
            f"[^\\s/~.:<>{token_barred}][^\\s:<>{token_barred}]*\\.md\\b",
        ]
    )
    return f"{_TOKEN_START}({paths})"
