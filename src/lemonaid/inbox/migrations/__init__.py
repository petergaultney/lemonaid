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
from collections.abc import Callable


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
    """
    current_version = get_current_version(conn)
    migrations = discover_migrations()
    applied = []

    for version, description, migrate_fn in migrations:
        if version > current_version:
            migrate_fn(conn)
            set_version(conn, version)
            conn.commit()
            applied.append(f"v{version}: {description}")

    return applied
