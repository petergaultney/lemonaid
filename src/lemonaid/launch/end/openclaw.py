"""Ending an OpenClaw lemon: no harness process or pane of its own to stop, since the gateway
runs a session only while it has a turn. Its doc watches stop, and its session is archived in
OpenClaw, which keeps the transcript; a new message there brings session and lemon back.
"""

import pathlib
import subprocess

from ...openclaw import sessions
from ...watch import openclaw_cli, watch_list

_ARCHIVE_SECONDS = 30


def watched(session_key: str) -> list[str]:
    path = openclaw_cli.list_path(watch_list.default_lists_dir(), session_key)
    return list(watch_list.peek(path))


def stop_watches(session_key: str) -> list[str]:
    """Stop every watch *session_key* holds; its waiter exits on the emptied list."""
    path = openclaw_cli.list_path(watch_list.default_lists_dir(), session_key)
    return [
        f"stopped watching {doc}"
        for doc in watched(session_key)
        if watch_list.remove(path, pathlib.Path(doc))
    ]


def archive(session_key: str) -> str:
    """Archive the session in OpenClaw, never deleting it; what happened, as a line."""
    try:
        done = subprocess.run(
            [sessions.cli(), "sessions", "archive", session_key],
            capture_output=True,
            text=True,
            timeout=_ARCHIVE_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return f"kept its OpenClaw session {session_key}: {error}"

    if done.returncode:
        why = done.stderr.strip() or f"openclaw exited {done.returncode}"
        return f"kept its OpenClaw session {session_key}: {why}"

    return f"archived its OpenClaw session {session_key}"
