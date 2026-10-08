"""Actionable briefs in the same inbox scope as teardown."""

import sqlite3

from rich.console import Console
from rich.text import Text

from ..brief import attached, colors, status
from ..inbox import db
from ..log import get_logger
from . import inbox_cleanup, target

_log = get_logger("places.toss_warning")


def affected(doomed: target.TossTarget) -> list[tuple[str, str]]:
    snapshot = inbox_cleanup.capture(doomed.session, doomed.places, doomed.closing)
    try:
        with db.connect() as conn:
            rows = [
                *snapshot.terminals,
                *(row for row_id in snapshot.daemon_ids if (row := db.get(conn, row_id))),
            ]
            paths = attached.by_channel(conn, (row.channel for row in rows))
    except sqlite3.Error as e:
        _log.warning("could not read briefs for toss confirmation: %s", e)
        return []

    result: dict[str, tuple[str, str]] = {}
    for row in rows:
        if path := paths.get(row.channel):
            try:
                parts = status.split(path.read_text())
            except OSError as e:
                _log.warning("could not read brief %s for toss confirmation: %s", path, e)
                continue

            if parts.status in {"merge", "approve", "blocked", "alert"}:
                result[row.channel] = (row.name or parts.title or row.channel, parts.status)
    return list(result.values())


def show(doomed: target.TossTarget) -> None:
    lemons = affected(doomed)
    if not lemons:
        return

    console = Console(stderr=True)
    console.print("Lemons awaiting action will leave the inbox:")
    for name, state in lemons:
        console.print(Text(f"  {name} ({state})", style=colors.status_text_style(state)))
