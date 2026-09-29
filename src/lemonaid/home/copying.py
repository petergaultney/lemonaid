"""Copying the old home's files into the new one, so a stop at any byte can be rerun.

Each file is written under a name only the migration uses, checked, and then
published with a hard link, which never replaces an existing file. A stopped
run leaves at most unpublished partial files, which a rerun or `--abort` removes.
"""

import os
import shutil
from pathlib import Path

from . import inventory, journal


def partial(target: Path, stamp: str) -> Path:
    """Where *target* is written before it is published. The migration's stamp in the
    name means cleanup only ever touches this migration's own partial files."""
    return target.with_name(f".{target.name}.lemonaid-migrate-{stamp}.tmp")


def remove_partials(record: journal.Journal) -> None:
    """Drop copies a stopped run left half-written; they were never published."""
    for entry in record.files():
        partial(inventory.destination(record.old, entry.relative), record.directory.name).unlink(
            missing_ok=True
        )


def _copy_one(source: Path, target: Path, sha256: str, stamp: str) -> str:
    written = partial(target, stamp)
    with source.open("rb") as reader, written.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())
    shutil.copystat(source, written)
    if inventory.sha256(written) != sha256:
        written.unlink()
        return f"{source} changed while it was copied"

    try:
        os.link(written, target)  # publishes the whole file, and never over an existing one
    except FileExistsError:
        written.unlink()
        return f"{target} appeared while it was being copied"

    written.unlink()
    return ""


def copy_all(record: journal.Journal) -> str:
    if unsafe := inventory.unsafe_destinations(
        inventory.destination(record.old, e.relative) for e in record.entries
    ):
        return unsafe[0]

    remove_partials(record)
    for entry in record.entries:
        target = inventory.destination(record.old, entry.relative)
        if entry.directory:
            target.mkdir(parents=True, exist_ok=True)
            continue

        if target.exists():
            if inventory.sha256(target) == entry.sha256:
                continue

            return f"{target} exists with other content"

        target.parent.mkdir(parents=True, exist_ok=True)
        if error := _copy_one(
            record.old / entry.relative, target, entry.sha256, record.directory.name
        ):
            return error

    return ""
