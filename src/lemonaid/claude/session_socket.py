"""Find a running Claude Code session's inbox socket and write a message to it.

Each session lists itself in `~/.claude/sessions/<pid>.json` with its `messagingSocketPath`.
One JSON line written to that socket starts a turn in an idle session, or is read at a busy
one's next tool call. Claude Code documents the socket but not the line a foreign sender
writes; `line` is derived from its binary (2.1.296) and pinned by a test.
"""

import json
import os
import socket
import typing as ty
import uuid
from pathlib import Path

FROM_NAME = "lemonaid"


class Refused(Exception):
    """The session didn't take the message: its socket is missing, refused it, or timed out."""


class Session(ty.NamedTuple):
    pid: int
    session_id: str
    cwd: str
    socket: str


def claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def _entries() -> ty.Iterator[Session]:
    for path in (claude_dir() / "sessions").glob("*.json"):
        try:
            data = json.loads(path.read_text())
            entry = Session(
                int(data["pid"]),
                str(data["sessionId"]),
                str(data.get("cwd") or ""),
                str(data.get("messagingSocketPath") or ""),
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if entry.socket and path.stem == str(entry.pid):
            yield entry


def find(session_id: str) -> Session | None:
    """The live session whose ID starts with *session_id* (a channel holds only 8 characters).

    None when no session matches, or more than one does.
    """
    if not session_id:
        return None

    found = [e for e in _entries() if e.session_id.startswith(session_id) and alive(e)]
    return found[0] if len(found) == 1 else None


def alive(entry: Session) -> bool:
    """Whether *entry*'s process still runs and still lists itself as that session."""
    try:
        os.kill(entry.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    try:
        data = json.loads((claude_dir() / "sessions" / f"{entry.pid}.json").read_text())
    except (OSError, ValueError):
        return False
    return data.get("sessionId") == entry.session_id


def line(text: str, msg_id: str) -> bytes:
    """*text* may quote other people (PR and document comments), so it can't close the wrapper."""
    body = text.replace("</cross-session-message", "&lt;/cross-session-message")
    content = f'<cross-session-message from-name="{FROM_NAME}">\n{body}\n</cross-session-message>'
    return (
        json.dumps(
            {
                "msgV": 1,
                "msg_id": msg_id,
                "type": "user",
                "priority": "next",
                "message": {"role": "user", "content": content},
            }
        )
        + "\n"
    ).encode()


def send(entry: Session, text: str) -> None:
    """Raises `Refused` when the session can't take it."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(10)
        try:
            sock.connect(entry.socket)
            sock.sendall(line(text, str(uuid.uuid4())))
        except OSError as error:
            raise Refused(f"{entry.socket}: {error}") from error
