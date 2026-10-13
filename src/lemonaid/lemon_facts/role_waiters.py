"""`lemon doctor --waiters`: the waiters each lemon's roles imply and doesn't have running."""

import json
import sqlite3
from collections import abc

from .. import brief
from ..brief import role_needs, role_report, roles
from ..watch import pr_open


def _missing(conn: sqlite3.Connection, lemon_id: str) -> list[role_needs.Need] | None:
    """None when the lemon isn't attached to a brief."""
    try:
        found = brief.lemon.attachment(conn, lemon_id)
    except (LookupError, ValueError):
        return None

    return role_report.missing(conn, found.path, found.channel, _is_open)


def _is_open(pr: roles.PR) -> bool:
    return pr_open.is_open(pr.repo, pr.number)


def run(conn: sqlite3.Connection, lemon_ids: abc.Iterable[str], as_json: bool) -> bool:
    """Print what each lemon is missing; whether any lemon is missing a waiter."""
    found = {lemon_id: _missing(conn, lemon_id) for lemon_id in lemon_ids}
    short = {lemon_id: needs for lemon_id, needs in found.items() if needs}
    if as_json:
        print(
            json.dumps(
                {
                    "missing": {
                        lemon_id: [
                            {"kind": n.kind, "target": n.target, "command": n.command}
                            for n in needs
                        ]
                        for lemon_id, needs in short.items()
                    },
                    "skipped": [lemon_id for lemon_id, needs in found.items() if needs is None],
                }
            )
        )
        return bool(short)

    print(f"{len(found)} lemons, {len(short)} missing role waiters")
    for lemon_id, needs in short.items():
        print(lemon_id)
        for need in needs:
            print(f"  {need.reason}: {need.command}")
    return bool(short)
