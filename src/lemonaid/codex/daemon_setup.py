"""Whether Codex is set to leave the shared app-server daemon off."""

import os
import tomllib
from pathlib import Path

from ..log import get_logger

_log = get_logger("codex.daemon_setup")


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def daemon_auto_start_warning(home: Path) -> list[str]:
    """Lines warning that `features.daemon_auto_start` is not `false`; empty when Codex isn't installed or it is."""
    if not home.is_dir():
        return []

    try:
        features = tomllib.loads((home / "config.toml").read_text()).get("features", {})
    except FileNotFoundError:
        features = {}
    except (tomllib.TOMLDecodeError, OSError) as exc:
        _log.warning("cannot read %s: %s", home / "config.toml", exc)
        return []

    if features.get("daemon_auto_start") is False:
        return []

    return [
        "Codex daemon",
        "  `daemon_auto_start = false` is not set under [features] in ~/.codex/config.toml.",
        "  Codex lemons on the shared app-server record no tty, so switching to them can misroute.",
        '  See docs/codex.md, under "Switching to pane doesn\'t work"',
    ]
