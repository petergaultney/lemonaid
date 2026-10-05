"""Read exact user handoff phrases from Codex transcript entries."""

import json

from ..codex import watcher as codex_watcher
from ..inbox import db
from . import handoff_state


def phrases(conn, row) -> None:
    for channel in (row["source"], row["target"]):
        if not channel.startswith("codex:"):
            continue

        notification = db.get_by_channel(conn, channel, unread_only=False)
        if notification is None:
            continue

        path = codex_watcher.get_session_path(
            channel.removeprefix("codex:"), str(notification.metadata.get("cwd") or "")
        )
        if path is None:
            continue

        try:
            with path.open(encoding="utf-8") as file:
                lines = file.readlines()[-100:]
        except OSError:
            continue

        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "response_item":
                continue

            payload = entry.get("payload", {})
            if payload.get("type") != "message" or payload.get("role") != "user":
                continue

            content = payload.get("content", [])
            if (
                not isinstance(content, list)
                or len(content) != 1
                or not isinstance(content[0], dict)
                or content[0].get("type") != "input_text"
            ):
                continue

            handoff_state.typed_message(conn, channel, content[0].get("text", ""))
