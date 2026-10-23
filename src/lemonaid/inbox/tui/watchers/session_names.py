"""Claude session titles that arrive after the inbox first named a session."""

import threading
import time
from collections import abc

from ....claude import notify
from ....log import get_logger
from ... import db

_log = get_logger("tui")


def upgrade(mtimes: dict[str, float]) -> bool:
    """Give each live Claude session the title its transcript now has; True if any changed.

    Claude names a session only once it has some content, so the name in the
    inbox starts as a tmux/cwd placeholder, and a long-running session's hooks
    alone would leave it there. *mtimes* remembers each transcript's
    modification time across calls, so an unchanged one is not read again.
    """
    with db.connect(timeout=db.UI_TIMEOUT_SECONDS) as conn:
        candidates = [
            (
                n.id,
                n.metadata.get("session_id", ""),
                n.metadata.get("cwd", ""),
                n.metadata.get("transcript_path"),
            )
            for n in db.get_active(conn, switch_source=None)
            if n.channel.startswith("claude:")
            and n.metadata.get("name_source") not in ("claude_rename", "claude_index")
            and n.metadata.get("session_id")
            and n.metadata.get("cwd")
        ]

    upgraded = False
    for notification_id, session_id, cwd, transcript_path in candidates:
        transcript = notify.find_transcript(session_id, cwd, transcript_path)
        if not transcript:
            continue

        # resolve_session_name reads the full transcript, which can be
        # megabytes. With 60+ sessions this dominates CPU when nothing
        # has changed.
        cache_key = str(transcript)
        try:
            mtime = transcript.stat().st_mtime
        except OSError:
            continue

        if mtime == mtimes.get(cache_key):
            continue

        mtimes[cache_key] = mtime
        resolved = notify.resolve_session_name(session_id, cwd, transcript_path)
        if not resolved:
            continue

        with db.connect(timeout=db.UI_TIMEOUT_SECONDS) as conn:
            if db.refresh_auto_name(conn, notification_id, resolved.name, resolved.source):
                upgraded = True
                _log.info(
                    "name upgraded: %d -> %r (%s)",
                    notification_id,
                    resolved.name,
                    resolved.source,
                )

    return upgraded


_RESCAN_SECONDS = 20


class Scanner:
    """Runs `upgrade` off the event loop, at most every 20 seconds: resolving a title
    reads a transcript, which is too slow to do on every refresh tick.
    """

    def __init__(self) -> None:
        self._mtimes: dict[str, float] = {}
        self._last = 0.0

    def maybe_scan(self, upgraded: abc.Callable[[], None]) -> None:
        """Start a scan if one is due; `upgraded` runs, on the scan's thread, if a name changed."""
        now = time.time()
        if now - self._last < _RESCAN_SECONDS:
            return

        def scan() -> None:
            if upgrade(self._mtimes):
                upgraded()

        self._last = now
        threading.Thread(target=scan, daemon=True).start()
