"""Sending a message to the lemon a brief belongs to, as `lemonaid tell` does."""

import os
from pathlib import Path

from .. import brief
from ..inbox import db
from . import service, store


def send(path: Path, body: str) -> Path:
    """Queue *body* in the inbox of the lemon whose brief is *path*, from the person running this.

    Raises ValueError when the brief has no valid Lemon-ID, the message is
    empty, or messaging is paused. A brief with no lemon running keeps its
    messages in its inbox until one starts.
    """
    with db.connect() as conn:
        lemon_id = brief.identity.ensure(conn, path)
        channels = [
            entry.channel
            for entry in brief.attached.everything(conn)
            if entry.path.resolve() == path.resolve()
        ]

    sent = store.send(store.inbox_for_id(lemon_id), body, os.environ.get("USER") or "unknown")
    if any(channel.startswith("codex:") for channel in channels):
        service.ensure_running()

    return sent
