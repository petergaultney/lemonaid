"""Read exact user handoff phrases from Codex transcript entries."""

import json

from .. import auto_read
from ..codex import watcher as codex_watcher
from ..inbox import db
from ..lemon_watchers import read_jsonl_tail
from . import handoff_state


def has_ready_marker(conn, row) -> bool:
    """Read a standalone ready marker from the outgoing Codex final reply."""
    channel = row["source"]
    if not channel.startswith("codex:"):
        return False

    notification = db.get_by_channel(conn, channel, unread_only=False)
    if notification is None:
        return False

    transcript = codex_watcher.get_session_path(
        channel.removeprefix("codex:"), str(notification.metadata.get("cwd") or "")
    )
    if transcript is None:
        return False

    try:
        recent = list(auto_read.newest_first(read_jsonl_tail(transcript, max_bytes=256 * 1024)))
    except OSError:
        return False

    if not _latest_turn_completed(recent):
        return False

    marker = f"Handoff-Ready: {row['token']}"
    return marker in _final_message(recent).splitlines()


def _latest_turn_completed(recent: list[dict]) -> bool:
    """Whether Codex's newest turn ended normally, rather than being active or aborted."""
    for entry in recent:
        if entry.get("type") != "event_msg":
            continue
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        event = payload.get("type")
        if event == "task_complete":
            return True
        if event in ("task_started", "turn_aborted"):
            return False
    return False


def _final_message(recent: list[dict]) -> str:
    """Read the latest assistant prose from the newest completed turn."""
    for entry in recent:
        if entry.get("type") == "event_msg":
            payload = entry.get("payload")
            if not isinstance(payload, dict):
                continue
            event = payload.get("type")
            if event == "task_started":
                return ""
            if event == "agent_message" and isinstance(payload.get("message"), str):
                return payload["message"]
            continue

        if entry.get("type") != "response_item":
            continue
        payload = entry.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "message":
            continue
        if payload.get("role") != "assistant":
            continue
        content = payload.get("content")
        if not isinstance(content, list):
            continue
        text = "\n".join(
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") in ("output_text", "text")
            and isinstance(block.get("text"), str)
        )
        if text:
            return text
    return ""


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
