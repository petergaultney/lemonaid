"""A Codex lemon's conversation, from the items its rollout records as completed."""

from collections import abc
from pathlib import Path

from . import entry


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    return "\n".join(
        str(part.get("text") or "") for part in content if isinstance(part, dict)
    ).strip()


def _entries(item: dict, at: str, queued: bool | None) -> abc.Iterator[entry.Entry]:
    """*queued* is None when the turn's start is not in what was read."""
    match item.get("type"):
        case "UserMessage":
            if text := _text(item.get("content")):
                yield (
                    entry.Entry(entry.USER, text, at)
                    if queued is False
                    else entry.Entry(entry.OTHER, text, at, "queue" if queued else "")
                )
        case "AgentMessage":
            if text := _text(item.get("content")):
                yield entry.Entry(entry.LEMON, text, at)
        case "CommandExecution":
            yield entry.Entry(entry.TOOL, entry.one_line(f"exec: {item.get('command', '')}"), at)


def _conversation(records: abc.Iterable[dict]) -> abc.Iterator[entry.Entry]:
    """A turn's `task_started` says what started it. In a turn `codex queue` started, such as
    lemonaid's mail and watch events, the first user message is the queued input; any later
    one was typed into the turn. A read that starts mid-turn can't tell, so it doesn't call
    that turn's first message the user's."""
    queued: bool | None = None
    for record in records:
        payload = record.get("payload") or {}
        if record.get("type") != "event_msg":
            continue

        if payload.get("type") == "task_started":
            queued = (payload.get("turn_attribution") or {}).get("turn_trigger") == "queue"
        elif payload.get("type") == "item_completed":
            item = payload.get("item") or {}
            yield from _entries(item, str(record.get("timestamp") or ""), queued)
            if item.get("type") == "UserMessage":
                queued = False


def read(rollout: Path, limit: int) -> list[entry.Entry]:
    """The rollout's newest *limit* messages and the tool calls among them, oldest first."""
    return entry.newest(_conversation(entry.tail_records(rollout)), limit)
