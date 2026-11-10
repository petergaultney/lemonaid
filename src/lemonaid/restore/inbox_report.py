"""One inbox row, `lemonaid:restore`, naming every lost lemon restore could not bring back."""

import sqlite3
from collections import abc

from ..inbox import db, ended
from . import report

CHANNEL = "lemonaid:restore"


def post(conn: sqlite3.Connection, results: abc.Iterable[report.Result]) -> list[report.Result]:
    """Record each lemon restore could not bring back on its row and in the report row, or
    archive the report row when none is left; returns those lemons."""
    missing = [r for r in results if r.outcome not in report.OK]
    for result in missing:
        if result.outcome == report.NOT_RESTORED:
            db.restore_failed(conn, result.channel, result.detail)

    if not missing:
        db.archive_channel(
            conn, CHANNEL, "every lost lemon is back", cause=ended.ARCHIVED, by="restore"
        )
        return []

    listed = "; ".join(
        f"{r.name}: {r.outcome}" + (f" ({r.detail})" if r.detail else "") for r in missing
    )
    db.add(
        conn, CHANNEL, f"{len(missing)} not back to work after restore: {listed}", name="restore"
    )
    return missing
