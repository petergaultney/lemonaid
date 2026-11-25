"""An OpenClaw lemon's conversation, from the gateway's `chat.history`.

The gateway marks input from someone other than the session's owner with `senderIsOwner:
false`: a person writing in the chat itself, whom it names, or the scout's mail, which it doesn't.
OpenClaw's own clients, such as the web grove's `chat.send`, are the owner.
"""

import datetime
import json
import subprocess
from collections import abc

from . import entry

_TIMEOUT_SECONDS = 30


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


def _entries(message: dict) -> abc.Iterator[entry.Entry]:
    at = _at(message.get("timestamp"))
    content = message.get("content")
    match message.get("role"):
        case "user":
            text = content if isinstance(content, str) else ""
            mark = message.get("__openclaw") or {}
            if text.strip():
                yield (
                    entry.Entry(entry.OTHER, text, at, _sender(mark))
                    if mark.get("senderIsOwner") is False
                    else entry.Entry(entry.USER, text, at)
                )
        case "assistant" if isinstance(content, list):
            for block in content:
                if block.get("type") == "text" and str(block.get("text") or "").strip():
                    yield entry.Entry(entry.LEMON, block["text"], at)
                elif block.get("type") == "toolCall":
                    yield entry.Entry(entry.TOOL, _tool(block), at)


def _history(session_key: str, cli: str, limit: int) -> subprocess.CompletedProcess[str]:
    params = json.dumps({"sessionKey": session_key, "limit": limit})
    return subprocess.run(
        [cli, "gateway", "call", "chat.history", "--json", "--params", params],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
    )


def read(session_key: str, cli: str, limit: int) -> list[entry.Entry]:
    """The session's newest entries, oldest first. Raises OSError when the gateway can't answer."""
    try:
        done = _history(session_key, cli, limit)
    except subprocess.TimeoutExpired as error:
        raise OSError(f"chat.history took longer than {_TIMEOUT_SECONDS}s") from error

    if done.returncode != 0:
        raise OSError(done.stderr.strip() or f"chat.history exited {done.returncode}")

    try:
        messages = json.loads(done.stdout).get("messages") or []
    except json.JSONDecodeError as error:
        raise OSError(f"chat.history said something other than JSON: {error}") from error

    return [
        each for message in messages if isinstance(message, dict) for each in _entries(message)
    ][-limit:]
