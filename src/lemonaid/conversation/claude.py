"""A Claude lemon's conversation, from its session transcript."""

from collections import abc
from pathlib import Path

from . import entry


def _blocks(content: object) -> abc.Iterator[dict]:
    if isinstance(content, str):
        yield {"type": "text", "text": content}
    elif isinstance(content, list):
        yield from (block for block in content if isinstance(block, dict))


def _tool(block: dict) -> str:
    given = block.get("input") or {}
    detail = given.get("command") or given.get("file_path") or given.get("description") or ""
    return entry.one_line(
        f"{block.get('name', 'tool')}: {detail}" if detail else block.get("name", "tool")
    )


def _entries(record: dict) -> abc.Iterator[entry.Entry]:
    message = record.get("message") or {}
    at = str(record.get("timestamp") or "")
    if record.get("type") == "assistant":
        for block in _blocks(message.get("content")):
            if block.get("type") == "text" and block.get("text", "").strip():
                yield entry.Entry(entry.LEMON, block["text"], at)
            elif block.get("type") == "tool_use":
                yield entry.Entry(entry.TOOL, _tool(block), at)
        return

    origin = record.get("origin") or {}
    kind = origin.get("kind") if isinstance(origin, dict) else None
    if record.get("type") != "user" or (
        record.get("isMeta") and kind != "peer"
    ):  # peer mail is meta
        return

    text = "\n".join(
        block.get("text", "")
        for block in _blocks(message.get("content"))
        if block.get("type") == "text"
    ).strip()
    if not text:  # tool results come back as user records
        return

    if kind == "human":
        yield entry.Entry(entry.USER, text, at)
    else:
        yield entry.Entry(
            entry.OTHER,
            str(origin.get("body") or text) if kind == "peer" else text,
            at,
            str(origin.get("name") or kind or ""),
        )


def read(transcript: Path, limit: int) -> list[entry.Entry]:
    """The transcript's newest *limit* messages and the tool calls among them, oldest first."""
    return entry.newest(
        (each for record in entry.tail_records(transcript) for each in _entries(record)), limit
    )
