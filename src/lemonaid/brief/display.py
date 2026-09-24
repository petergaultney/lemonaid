"""Path formatting shared by the brief header and body."""

from pathlib import Path


def home_path(path: Path) -> str:
    try:
        return f"~/{path.expanduser().relative_to(Path.home())}"
    except ValueError:
        return str(path.expanduser())
