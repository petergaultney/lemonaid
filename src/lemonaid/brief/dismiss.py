"""Letting the tmux key that opened the popup also close it.

While a popup is open it receives every key, so tmux never sees prefix + b
there. The pager inside is given the same key sequence as a quit command.
"""

import subprocess
from collections import abc

_TMUX_QUERY_TIMEOUT_SECONDS = 0.5
_LESSKEY_ESCAPED = set("^ #\\;")


def _lesskey_key(tmux_key: str) -> str | None:
    """A tmux key name as lesskey writes it, or None when lesskey can't express it."""
    key = tmux_key.removeprefix("\\") if len(tmux_key) == 2 else tmux_key
    if key == "Escape":
        return "\\e"

    if len(key) == 3 and key.startswith("C-") and key[2].isalpha():
        return f"^{key[2].upper()}"

    if len(key) == 1 and key.isprintable():
        return f"\\{key}" if key in _LESSKEY_ESCAPED else key

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
    """Lesskey strings for every prefix followed by every brief-popup key."""
    return [
        f"{p}{k}"
        for prefix in prefixes
        if (p := _lesskey_key(prefix))
        for key in _brief_keys(prefix_table)
        if (k := _lesskey_key(key))
    ]


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
