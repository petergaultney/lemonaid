"""A document's version during a batch, including a temporarily missing file."""

from pathlib import Path


def of(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return 0
