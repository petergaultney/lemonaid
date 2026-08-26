"""Database migrations for lemonaid inbox.

Uses SQLite's PRAGMA user_version to track schema version.
Each migration module should have:
- VERSION: int - the version this migration brings us to
- DESCRIPTION: str - what this migration does
- migrate(conn) - function that performs the migration
"""

import importlib
import pkgutil
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager


@contextmanager
def _exclusive(conn: sqlite3.Connection) -> Iterator[None]:
    """Hold a write lock for the block, so no other connection can migrate too.

    `PRAGMA user_version` is not transactional, but the lock is what matters:
    the second connection waits, and by the time it reads the version the first
    has finished and committed.
    """
    conn.execute("BEGIN EXCLUSIVE")
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version from the database."""
    return conn.execute("PRAGMA user_version").fetchone()[0]


def set_version(conn: sqlite3.Connection, version: int) -> None:
    """Set the schema version in the database."""
    conn.execute(f"PRAGMA user_version = {version}")


def discover_migrations() -> list[tuple[int, str, Callable[[sqlite3.Connection], None]]]:
    """Discover all migration modules and return sorted list of (version, description, migrate_fn)."""
    migrations = []

    # Import all modules in this package
    package_path = __path__  # type: ignore[name-defined]
    for _importer, modname, ispkg in pkgutil.iter_modules(package_path):
        if modname.startswith("m") and not ispkg:
            module = importlib.import_module(f".{modname}", __package__)
            if hasattr(module, "VERSION") and hasattr(module, "migrate"):
                migrations.append(
                    (module.VERSION, getattr(module, "DESCRIPTION", ""), module.migrate)
                )

    # Sort by version
    migrations.sort(key=lambda x: x[0])
    return migrations


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Run any pending migrations.

    Returns list of descriptions of migrations that were run.

    Every `connect()` calls this, and the TUI connects from its watcher thread
    while the main thread is doing the same - so the version is read and written
    inside one exclusive transaction. Reading it outside, both connections saw
    the same pending migration and both applied it, and the second failed on a
    column the first had already renamed.
    """
    with _exclusive(conn):
        current_version = get_current_version(conn)
        applied = []

        for version, description, migrate_fn in discover_migrations():
            if version > current_version:
                migrate_fn(conn)
                set_version(conn, version)
                applied.append(f"v{version}: {description}")

    return applied
