"""An OpenClaw lemon's conversation, from the gateway's `chat.history`.

The gateway marks input from someone other than the session's owner with `senderIsOwner:
false`: a person writing in the chat itself, whom it names, or the scout's mail, which it doesn't.
OpenClaw's own clients, such as the web grove's `chat.send`, are the owner. A session another
session spawned starts with that session's task for it, which the gateway doesn't mark at all.
"""

import datetime
import json
from collections import abc

from ..openclaw import gateway, turns
from . import entry

_TIMEOUT_SECONDS = 30
_PAGE = 500  # messages per `chat.history` call
_MOST = 2000  # messages read back at most, for a session that is nearly all tool calls


def _at(milliseconds: object) -> str:
    try:
        return datetime.datetime.fromtimestamp(
            int(str(milliseconds)) / 1000, datetime.UTC
        ).isoformat()
    except ValueError:
        return ""


def _tool(block: dict) -> str:
    given = block.get("arguments") or {}
    detail = given.get("command", "") if isinstance(given, dict) else ""
    return entry.one_line(
        f"{block.get('name', 'tool')}: {detail}" if detail else block.get("name", "tool")
    )


def _sender(mark: dict) -> str:
    name = str(mark.get("senderName") or "")
    chat = str((mark.get("transport") or {}).get("channel") or "")
    return f"{name} \u00b7 {chat.capitalize()}" if name and chat else name or "mail"


def _files(mark: dict) -> tuple[tuple[str, int], ...]:
    """The files the gateway kept with a message, as it records them under `media`."""
    return tuple(
        (str(each.get("fileName") or "file"), int(each.get("sizeBytes") or 0))
        for each in mark.get("media") or ()
        if isinstance(each, dict)
    )


def _entries(message: dict, spawner: str) -> abc.Iterator[entry.Entry]:
    """*spawner* names the session that spawned this one, if one did."""
    at = _at(message.get("timestamp"))
    content = message.get("content")
    match message.get("role"):
        case "user":
            text = content if isinstance(content, str) else ""
            mark = message.get("__openclaw") or {}
            files = _files(mark)
            if not text.strip() and not files:
                return

            if spawner and mark.get("seq") == 1:
                yield entry.Entry(entry.OTHER, text, at, spawner, files)
            elif mark.get("senderIsOwner") is False:
                yield entry.Entry(entry.OTHER, text, at, _sender(mark), files)
            else:
                yield entry.Entry(entry.USER, text, at, files=files)
        case "assistant" if isinstance(content, list):
            for block in content:
                if block.get("type") == "text" and str(block.get("text") or "").strip():
                    yield entry.Entry(entry.LEMON, block["text"], at)
                elif block.get("type") == "toolCall":
                    yield entry.Entry(entry.TOOL, _tool(block), at)


def _page(
    session_key: str, cli: str, offset: int, named: abc.Callable[[str], str]
) -> tuple[list[entry.Entry], bool]:
    """The entries of the page *offset* messages back from the newest, and whether older ones
    remain."""
    found = gateway.call(
        cli,
        "chat.history",
        {"sessionKey": session_key, "limit": _PAGE, "offset": offset},
        _TIMEOUT_SECONDS,
    )
    messages = found.get("messages") or []
    parent = str((found.get("sessionInfo") or {}).get("spawnedBy") or "")
    spawner = named(parent) if parent else ""
    return [
        each
        for message in messages
        if isinstance(message, dict)
        for each in _entries(message, spawner)
    ], bool(found.get("hasMore"))


def mark(session_key: str, cli: str) -> str:
    """What changes whenever the session's conversation does, from its newest message alone.
    Raises OSError when the gateway can't answer."""
    found = gateway.call(
        cli, "chat.history", {"sessionKey": session_key, "limit": 1}, _TIMEOUT_SECONDS
    )
    newest = (found.get("messages") or [{}])[-1]
    return json.dumps(
        [
            found.get("sessionId"),
            found.get("totalMessages"),
            (newest.get("__openclaw") or {}).get("id"),
        ]
    )


def read(
    session_key: str, cli: str, limit: int, named: abc.Callable[[str], str]
) -> list[entry.Entry]:
    """The session's newest *limit* messages and the tool calls among them, oldest first, with
    another session *named* by its key. Raises OSError when the gateway can't answer.

    `chat.history` counts each tool call and each tool result as a message, so a busy session's
    newest page may hold only a few lines of talk; pages are read back until there are *limit*."""
    found: list[entry.Entry] = []
    for offset in range(0, _MOST, _PAGE):
        page, more = _page(session_key, cli, offset, named)
        found = page + found
        if not more or sum(each.role != entry.TOOL for each in found) >= limit:
            break

    return entry.newest(found, limit)


def with_failures(entries: abc.Iterable[entry.Entry], session_key: str) -> list[entry.Entry]:
    """*entries* with each turn on *session_key* that failed since this process started, by its
    time among them; one from before the oldest entry is left out."""
    found, times, last = list(entries), [], None
    for each in found:
        last = datetime.datetime.fromisoformat(each.at) if each.at else last
        times.append(last)
    oldest = next((at for at in times if at), None)
    if oldest is None:
        return found

    failed = [
        (when, entry.Entry(entry.FAILED, failure.why or "the turn failed", _at(failure.at_ms)))
        for failure in turns.failed(session_key)
        if (when := datetime.datetime.fromtimestamp(failure.at_ms / 1000, datetime.UTC)) >= oldest
    ]
    merged = [
        (at or oldest, 0, i, each) for i, (at, each) in enumerate(zip(times, found, strict=False))
    ]
    merged += [(when, 1, i, each) for i, (when, each) in enumerate(failed)]
    return [each for *_, each in sorted(merged, key=lambda m: m[:3])]
