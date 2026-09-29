"""A migration's record in `~/.lemons/migrations/<stamp>/`, and the DB path rewrite."""

import dataclasses
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from . import inventory, layout


@dataclasses.dataclass(frozen=True)
class Journal:
    directory: Path
    old: Path
    entries: list[inventory.Entry]

    @property
    def backup(self) -> Path:
        """Where the old home is kept once the migration has moved past it."""
        return self.directory / "brief-lemons"

    def files(self) -> list[inventory.Entry]:
        return [e for e in self.entries if not e.directory]


def write_atomic(path: Path, text: str) -> None:
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def create(directory: Path, found: inventory.Plan) -> Journal:
    """Write the inventory, the step that makes a started migration one a rerun continues."""
    record = {"old": str(found.old), "entries": [dataclasses.asdict(e) for e in found.entries]}
    write_atomic(directory / "inventory.json", json.dumps(record, indent=1))
    return Journal(directory, found.old, found.entries)


def load(directory: Path) -> Journal:
    record = json.loads((directory / "inventory.json").read_text())
    entries = [inventory.Entry(**e) for e in record["entries"]]
    return Journal(directory, Path(record["old"]), entries)


def directory_for(stamp: str) -> Path:
    return layout.lemons_dir() / "migrations" / stamp


def for_stamp(stamp: str) -> Journal | None:
    """The journal for *stamp*, or None if its migration stopped before writing one."""
    directory = directory_for(stamp)
    return load(directory) if (directory / "inventory.json").exists() else None


def rewrite_paths(conn: sqlite3.Connection, found: Journal, forward: bool) -> int:
    """Point every DB path at the new home (*forward*) or back at the old one, in one transaction."""
    pairs = [
        (str(found.old / e.relative), str(inventory.destination(found.old, e.relative)))
        for e in found.files()
    ]
    changed = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        for old, new in pairs:
            source, target = (old, new) if forward else (new, old)
            for table in inventory.PATH_TABLES:
                changed += conn.execute(
                    f"UPDATE {table} SET path = ? WHERE path = ?", (target, source)
                ).rowcount
        conn.commit()
    except BaseException:
        conn.rollback()
        raise

    return changed
