"""The configured plugins, for the commands and readers that start from the config file."""

import functools
from pathlib import Path

from .. import config
from ..plugins.command import Plugin
from .plugin import defaults


@functools.cache
def _as_of(path: Path, changed: float) -> tuple[Plugin, ...]:
    return config.load_config(path).watch.doc_plugins


def plugins() -> tuple[Plugin, ...]:
    """Read again only when the config file changes, since the inbox asks on every refresh."""
    path = config.get_config_path()
    try:
        changed = path.stat().st_mtime
    except OSError:
        return defaults()

    return _as_of(path, changed)
