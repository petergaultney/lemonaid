"""The `[web]` table: keys in the grove's pages in a browser (`lemonaid grove serve`).

Keys are named as a browser's `KeyboardEvent.key` names them, or `C-` and a letter for one with
Control, or `Space`, or `prefix` for the prefix key again.
"""

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class WebConfig:
    prefix: str = "`"  # pressed first, as tmux's prefix is
    home: str = "prefix"  # after the prefix: back to the grove
    literal: str = "h"  # after the prefix: type the prefix itself
    brief: str = "b"  # after the prefix: focus a lemon's brief


def _key(name: str, raw: object, default: str) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()

    print(f"Warning: [web] {name} must be a key name, such as ` or Space", file=sys.stderr)
    return default


def parse(data: dict) -> WebConfig:
    return WebConfig(
        *(
            _key(name, data.get(name, default), default)
            for name, default in (
                ("prefix", WebConfig.prefix),
                ("home", WebConfig.home),
                ("literal", WebConfig.literal),
                ("brief", WebConfig.brief),
            )
        )
    )
