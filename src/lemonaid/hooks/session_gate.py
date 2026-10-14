"""A cheap shell-visible hint that a session has an attached brief."""

from pathlib import Path

from ..watch import own_edits


def mark(own_root: Path, writer: str, brief: Path | None) -> None:
    if not writer:
        return
    path = own_edits.writer_dir(own_root, writer) / "brief"
    if brief is None:
        path.unlink(missing_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != str(brief):
            path.write_text(str(brief))
