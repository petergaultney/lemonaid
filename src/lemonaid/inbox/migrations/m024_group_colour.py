"""Placeholder: a stored group colour was tried and dropped.

Databases that ran it carry an unused `colour` column on `lemon_groups`; the
version stays so numbering is the same everywhere.
"""

import sqlite3

VERSION = 24
DESCRIPTION = "Reserved (unused group colour column)"


def migrate(conn: sqlite3.Connection) -> None:
    pass
