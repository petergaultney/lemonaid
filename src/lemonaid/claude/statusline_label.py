"""The `[claude.statusline] label_color` setting: how the session name is drawn."""

import os
import sys
import tomllib
from pathlib import Path

_DEFAULT = "\033[38;5;248m"  # mid-gray, readable on dark and light backgrounds


def _config_path() -> Path:
    if override := os.environ.get("LEMONAID_CONFIG"):
        return Path(override).expanduser()

    return Path.home() / ".config" / "lemonaid" / "config.toml"


def _escape(raw: object) -> str:
    if raw == "dim":
        return "\033[2m"

    if raw == "default":
        return ""

    if isinstance(raw, int) and not isinstance(raw, bool) and 0 <= raw <= 255:
        return f"\033[38;5;{raw}m"

    print(
        f'Warning: [claude.statusline] label_color must be "dim", "default" or 0-255, not {raw!r}',
        file=sys.stderr,
    )
    return _DEFAULT


def label_escape(config_path: Path | None = None) -> str:
    """The escape sequence that precedes the session name; empty means the default foreground."""
    try:
        raw = tomllib.loads((config_path or _config_path()).read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return _DEFAULT

    claude = raw.get("claude")
    table = claude.get("statusline") if isinstance(claude, dict) else None
    if not isinstance(table, dict) or "label_color" not in table:
        return _DEFAULT

    return _escape(table["label_color"])
