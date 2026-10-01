"""Letting the tmux key that opened the popup also close it.

While a popup is open it receives every key, so tmux never sees prefix + b
there. The app inside is given the same key sequence to close on, as the two
keys it arrives as: each a character, or Textual's name for it (`ctrl+b`).
"""

import subprocess
from collections import abc

_TMUX_QUERY_TIMEOUT_SECONDS = 0.5


def _key(tmux_key: str) -> str | None:
    """A tmux key name as Textual reports it, or None for a key this doesn't translate."""
    key = tmux_key.removeprefix("\\") if len(tmux_key) == 2 else tmux_key
    if key == "Escape":
        return "escape"

    if len(key) == 3 and key.startswith("C-") and key[2].isalpha():
        return f"ctrl+{key[2].lower()}"

    if len(key) == 1 and key.isprintable():
        return key

    return None


def _brief_keys(prefix_table: str) -> list[str]:
    """Keys in `tmux list-keys -T prefix` output whose command shows a brief popup."""
    keys = []
    for line in prefix_table.splitlines():
        tokens = line.split()
        if "brief show" not in line or "prefix" not in tokens:
            continue

        keys.append(tokens[tokens.index("prefix") + 1])

    return keys


def sequences(prefixes: abc.Iterable[str], prefix_table: str) -> list[str]:
    """Every prefix followed by every brief-popup key, as `<prefix> <key>`."""
    return [
        f"{p} {k}"
        for prefix in prefixes
        if (p := _key(prefix))
        for key in _brief_keys(prefix_table)
        if (k := _key(key))
    ]


def pairs(sequences: abc.Iterable[str]) -> list[tuple[str, str]]:
    """`sequences`' strings as (prefix, key), skipping any that is not two keys."""
    split = [sequence.partition(" ") for sequence in sequences]
    return [(first, second) for first, _, second in split if second]


def _tmux(*args: str) -> str:
    try:
        result = subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=_TMUX_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""

    return result.stdout


def bound_sequences() -> list[str]:
    """The key sequences bound to the brief popup on this tmux server."""
    prefixes = [_tmux("show", "-gv", option).strip() for option in ("prefix", "prefix2")]
    return sequences([p for p in prefixes if p and p != "None"], _tmux("list-keys", "-T", "prefix"))
