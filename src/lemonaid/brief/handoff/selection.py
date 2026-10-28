"""Resolve a handoff source through the shared lemon lookup or its brief path."""

import sqlite3

from .. import attached, lemon, store


def channel(conn: sqlite3.Connection, source: str = "", brief: str = "") -> str:
    if source:
        return lemon.attachment(conn, source, claim_pending=False).channel

    path = store.resolve(brief)
    if not store.outside_error(path) and path.is_file():
        holders = [item.channel for item in attached.everything(conn) if item.path == path]
        if len(holders) != 1 or not holders[0]:
            raise ValueError("The brief needs one attached outgoing channel")
        return holders[0]

    return lemon.attachment(conn, brief, claim_pending=False).channel
