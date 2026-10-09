"""Stable lemon identity stored in a brief and registered by its path.

Registering a Brief-ID this database has never seen also reads in the brief's
`Groups:` line, which is how groups follow a brief to another machine.
"""

import re
import sqlite3
import unicodedata
from pathlib import Path

from .. import groups
from . import store

_LINE = re.compile(r"(?:Brief-ID|Lemon-ID): (.+)")


def valid(lemon_id: str) -> bool:
    if not lemon_id or lemon_id.startswith(".") or lemon_id in (".", ".."):
        return False

    try:
        if len(lemon_id.encode("utf-8")) > 255:
            return False
    except UnicodeEncodeError:
        return False

    return not any(char in "/\\" or unicodedata.category(char).startswith("C") for char in lemon_id)


def brief_name(brief_id: str) -> str:
    """The name half of *brief_id*, or "" for an older brief ID without one."""
    return brief_id.rsplit(".", 1)[1] if "." in brief_id else ""


def brief_description(brief_id: str) -> str:
    """The description half of *brief_id*, before its name, if present."""
    return brief_id.rsplit(".", 1)[0] if brief_name(brief_id) else brief_id


def wordybin(lemon_id: str) -> str:
    """Compatibility alias for the name half of a brief ID."""
    return brief_name(lemon_id)


def markdown_id(brief_id: str) -> str:
    """Markdown for a brief ID, with its name bold and its description dimmed."""
    name = brief_name(brief_id)
    if not name:
        return f"`{brief_id}`"

    escaped_name = re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", name)
    return f"`{brief_description(brief_id)}`.**{escaped_name}**"


def by_channel(conn: sqlite3.Connection) -> dict[str, str]:
    """The brief ID of each session's attached brief."""
    return {
        row["channel"]: row["lemon_id"]
        for row in conn.execute(
            "SELECT b.channel, i.lemon_id FROM session_briefs b"
            " JOIN lemon_identities i ON i.path = b.path"
        )
    }


def read(text: str) -> str:
    header = text.split("\n## ", 1)[0]
    lines = [line for line in header.splitlines() if line.startswith(("Brief-ID:", "Lemon-ID:"))]
    if not lines:
        return ""

    if len(lines) != 1 or (match := _LINE.fullmatch(lines[0])) is None:
        raise ValueError("Brief has an invalid or duplicate Brief-ID line")

    lemon_id = match.group(1).rstrip()
    if "Brief-ID:" in lemon_id or "Lemon-ID:" in lemon_id:
        raise ValueError("Brief-ID line holds a second Brief-ID")

    if not valid(lemon_id):
        raise ValueError("Brief has an invalid or path-unsafe Brief-ID")

    return lemon_id


def _with_id(text: str, lemon_id: str) -> str:
    existing = read(text)
    if existing:
        if existing != lemon_id:
            raise ValueError("Brief-ID changed during migration")

        return text

    lines = text.splitlines(keepends=True)
    after = 1 if lines and lines[0].startswith("# ") else 0
    return "".join([*lines[:after], "\nBrief-ID: " + lemon_id + "\n", *lines[after:]])


def _path(path: Path) -> Path:
    if error := store.outside_error(path):
        raise ValueError(error)

    resolved = path.resolve()
    if resolved.parent != store.briefs_dir().resolve() or path.is_symlink():
        raise ValueError(f"Brief must be a file directly inside {store.briefs_dir()}: {path}")

    if not resolved.is_file():
        raise ValueError(f"No brief at {resolved}")

    return resolved


def from_path(path: Path) -> str:
    return read(_path(path).read_text())


def ensure(conn: sqlite3.Connection, path: Path, *, regenerate_on_collision: bool = False) -> str:
    """Backfill a legacy brief once, serializing concurrent assignments in SQLite."""
    path = _path(path)
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute(
            "SELECT lemon_id FROM lemon_identities WHERE path = ?", (str(path),)
        ).fetchone()
        recorded = existing["lemon_id"] if existing else ""
        if recorded and not valid(recorded):
            raise ValueError(f"Database has an invalid Lemon-ID for {path}")

        text = path.read_text()
        in_file = read(text)
        if recorded and in_file and recorded != in_file:
            raise ValueError(f"Lemon-ID in {path} disagrees with the database")

        generated = (not in_file and not recorded) or regenerate_on_collision
        lemon_id = in_file or recorded or store.new_lemon_id(path)
        while True:
            alias = conn.execute(
                "SELECT lemon_id FROM lemon_aliases WHERE old_id = ?", (lemon_id,)
            ).fetchone()
            if alias and generated:
                lemon_id = store.new_lemon_id(path)
                continue

            if alias:
                raise ValueError(f"Lemon-ID {lemon_id} is an old ID of {alias['lemon_id']}")

            holder = conn.execute(
                "SELECT path FROM lemon_identities WHERE lemon_id = ?", (lemon_id,)
            ).fetchone()
            if not holder or holder["path"] == str(path):
                break

            if generated:
                lemon_id = store.new_lemon_id(path)
                continue

            if Path(holder["path"]).exists():
                raise ValueError(f"Lemon-ID {lemon_id} already belongs to {holder['path']}")

            conn.execute(
                "UPDATE lemon_identities SET path = ? WHERE lemon_id = ?",
                (str(path), lemon_id),
            )
            break

        if not existing and not holder:
            conn.execute(
                "INSERT INTO lemon_identities (path, lemon_id) VALUES (?, ?)",
                (str(path), lemon_id),
            )
            if (names := groups.line.read(text)) is not None:
                groups.store.replace_memberships(conn, lemon_id, names)

        if not in_file:
            store.edit(path, lambda text: _with_id(text, lemon_id))
        elif in_file != lemon_id:
            store.edit(
                path,
                lambda text: _replace_header_id(text, in_file, lemon_id),
            )

        conn.commit()
        return lemon_id
    except BaseException:
        conn.rollback()
        raise


def _replace_header_id(text: str, old_id: str, new_id: str) -> str:
    header = text.split("\n## ", 1)[0]
    for label in ("Brief-ID:", "Lemon-ID:"):
        old_line = f"{label} {old_id}\n"
        if old_line in header:
            return text.replace(old_line, f"Brief-ID: {new_id}\n", 1)
    raise ValueError("Brief-ID line disappeared during migration")
