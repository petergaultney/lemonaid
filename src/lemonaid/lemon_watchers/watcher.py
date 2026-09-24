"""Unified session watcher infrastructure.

Provides shared watcher loop logic that can be used by multiple backends
(Claude, Codex, etc.) to monitor session files for activity.
"""

import json
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .. import tmux
from ..log import get_logger
from .common import ModelInfo

_log = get_logger("watcher")

# A hook can announce a session just before its transcript is created. Keep
# successful path lookups forever, but retry a miss instead of making that
# startup race permanent. The delay avoids repeatedly scanning backend session
# directories for rows that genuinely have no transcript.
_MISSING_SESSION_RETRY_SECONDS = 5.0


class WatcherBackend(Protocol):
    """Protocol for LLM-specific watcher backends."""

    CHANNEL_PREFIX: str

    @staticmethod
    def get_session_path(session_id: str, cwd: str) -> Path | None:
        """Get the session file path for a session."""
        ...

    @staticmethod
    def describe_activity(entry: dict) -> str | None:
        """Extract a human-readable description of activity from an entry."""
        ...

    @staticmethod
    def should_dismiss(entry: dict) -> bool:
        """Check if an entry indicates the notification should be dismissed."""
        ...

    @staticmethod
    def needs_attention(entry: dict) -> bool:
        """Check if an entry indicates the agent is waiting for user input.

        Optional method - returns False by default for backends that don't need it
        (e.g., Claude/Codex where hooks fire when attention is needed).
        """
        ...

    @staticmethod
    def get_model(entry: dict) -> ModelInfo | None:
        """Extract the model identity from an entry, when it carries one."""
        ...

    # Optional: backends can define read_lines(session_path: Path) -> list[str]
    # to override the default local file reader (e.g., for SSH).
    # Resolved via getattr() in the watch loop, falling back to read_jsonl_tail.


def read_jsonl_tail(path: Path, max_bytes: int = 64 * 1024) -> list[str]:
    """Read the last N bytes of a JSONL file and return lines.

    Seeks to the end minus max_bytes, skips the first partial line,
    and returns all complete lines.
    """
    try:
        file_size = path.stat().st_size
        read_size = min(file_size, max_bytes)

        with open(path, encoding="utf-8", errors="replace") as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                f.readline()  # Skip partial line
            content = f.read()

        return content.strip().split("\n")
    except (OSError, UnicodeDecodeError):
        return []


def parse_timestamp(ts_str: str) -> float | None:
    """Parse an ISO timestamp string to Unix timestamp."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def is_process_running_on_tty(tty: str, process_name: str = "claude") -> bool:
    """Check if a process is running on the given TTY.

    Args:
        tty: TTY path like "/dev/ttys002" or "ttys002"
        process_name: Process name to search for (default: "claude")

    Returns:
        True if the process is running on that TTY
    """
    # Normalize TTY name (remove /dev/ prefix if present)
    tty_name = tty.replace("/dev/", "")
    if not tty_name:
        return True  # Can't check, assume alive

    try:
        result = subprocess.run(
            ["ps", "-t", tty_name, "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return process_name in result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return True  # On error, assume alive to avoid false archiving


def get_latest_activity(
    session_path: Path,
    describe_activity: Callable[[dict], str | None],
    read_lines: Callable[[Path], list[str]] = read_jsonl_tail,
) -> tuple[str, str] | None:
    """Get the most recent describable activity from a session file.

    Returns (message, timestamp) tuple, or None if no activity found.
    The timestamp can be used to detect genuinely new activity.
    """
    lines = read_lines(session_path)

    # Most recent first, limit to last 50 entries
    for line in reversed(lines[-50:]):
        try:
            entry = json.loads(line)
            activity = describe_activity(entry)
            if activity:
                ts = entry.get("timestamp", "")
                return (activity, ts)
        except json.JSONDecodeError:
            continue

    if lines:
        _log.info("no activity found in %s (%d lines)", session_path.name, len(lines))

    return None


def has_activity_since(
    session_path: Path,
    since_time: float,
    should_dismiss: Callable[[dict], bool],
    read_lines: Callable[[Path], list[str]] = read_jsonl_tail,
) -> dict | None:
    """Check if session has dismiss-worthy activity since given timestamp.

    Returns the triggering entry if found, None otherwise.
    """
    lines = read_lines(session_path)

    for line in reversed(lines[-50:]):
        try:
            entry = json.loads(line)
            ts = parse_timestamp(entry.get("timestamp", ""))
            if ts and ts > since_time and should_dismiss(entry):
                return entry
        except json.JSONDecodeError:
            continue

    return None


def check_needs_attention(
    session_path: Path,
    since_time: float,
    needs_attention: Callable[[dict], bool],
    read_lines: Callable[[Path], list[str]] = read_jsonl_tail,
) -> dict | None:
    """Check if session has an entry indicating the agent needs user attention.

    Scans recent entries for "turn complete" signals (e.g., OpenClaw's stopReason: "stop").
    Returns the triggering entry if found, None otherwise.
    """
    lines = read_lines(session_path)

    for line in reversed(lines[-50:]):
        try:
            entry = json.loads(line)
            ts = parse_timestamp(entry.get("timestamp", ""))
            if ts and ts > since_time and needs_attention(entry):
                return entry
        except json.JSONDecodeError:
            continue

    return None


def _latest_model(
    entries: list[dict], get_model: Callable[[dict], ModelInfo | None]
) -> ModelInfo | None:
    return next((model for entry in entries if (model := get_model(entry))), None)


def _check_pane_exists(tty: str, switch_source: str | None, socket: str | None = None) -> bool:
    """Whether a pane still exists, assuming it does whenever we cannot tell.

    Deferred import to avoid circular dependencies.
    """
    if not switch_source:
        return True  # Can't check, assume exists

    from ..handlers import check_pane_exists_by_tty

    # A tmux that failed to answer is not a pane that is gone. Archiving on it
    # retires every live session at once, since one failed `list-panes` looks
    # exactly like every pane having disappeared.
    return check_pane_exists_by_tty(tty, switch_source, socket) is not False


_warned_no_tty: set[str] = set()


def _tmux_servers_needed(
    active: list[tuple[str, str, str, float, bool, str | None, str, str | None]],
    sockets: dict[str, str],
) -> set[str | None]:
    """Which tmux servers the active list talks to."""
    return {
        sockets.get(channel)
        for channel, _sid, _cwd, _created, _unread, tty, _msg, source in active
        if tty and source == "tmux"
    }


def _fetch_pane_locations(
    servers: set[str | None],
) -> dict[str | None, dict[str, tuple[str, str]] | None]:
    """One `tmux list-panes -a` per server, returning tty -> (session, window)."""
    return {socket: tmux.navigation.locations_by_tty(socket) for socket in servers}


def _record_locations(
    active: list[tuple[str, str, str, float, bool, str | None, str, str | None]],
    record_location: Callable[[str, str, str, str | None], None],
    sockets: dict[str, str],
    pane_locations: dict[str | None, dict[str, tuple[str, str]] | None],
) -> None:
    """Note where each tmux-hosted session is sitting, so it can be rebuilt later."""
    for channel, _sid, _cwd, _created, _unread, tty, _msg, source in active:
        if not (tty and source == "tmux"):
            continue

        socket = sockets.get(channel)
        server_panes = pane_locations.get(socket)
        if server_panes is None:
            continue
        location = server_panes.get(tty)
        if location is not None:
            record_location(channel, *location, socket)


def _archive_stale_sessions(
    active: list[tuple[str, str, str, float, bool, str | None, str, str | None]],
    archive_channel: Callable[[str], None],
    sockets: dict[str, str],
    pane_locations: dict[str | None, dict[str, tuple[str, str]] | None],
) -> set[str]:
    """Archive stale sessions based on TTY occupancy and pane existence.

    For each TTY:
    - If pane no longer exists: archive immediately (most reliable check)
    - If process is running: only one session can be active, archive others
    - If process is not running: archive all sessions on that TTY

    `pane_locations` is the pre-fetched result of one `tmux list-panes -a` per
    server, shared with `_record_locations` so tmux is only asked once per tick.

    Returns set of archived channel names.
    """
    archived: set[str] = set()

    def archive(
        item: tuple[str, str, str, float, bool, str | None, str, str | None],
        reason: str,
        **evidence: object,
    ) -> None:
        channel, session_id, cwd, created_at, _unread, tty, _message, source = item
        archive_channel(channel)
        archived.add(channel)
        details = " ".join(f"{key}={value!r}" for key, value in evidence.items())
        _log.info(
            "auto-archive channel=%s reason=%s session_id=%s tty=%s source=%s "
            "socket=%s cwd=%r created_at=%.3f%s",
            channel,
            reason,
            session_id,
            tty,
            source,
            sockets.get(channel),
            cwd,
            created_at,
            f" {details}" if details else "",
        )

    # First pass: archive any sessions whose panes no longer exist
    remaining = []
    for item in active:
        channel, _session_id, _cwd, _created_at, _is_unread, tty, _db_message, switch_source = item
        if tty and switch_source == "tmux":
            socket = sockets.get(channel)
            server_panes = pane_locations.get(socket)
            # server_panes is None when the server could not be reached -
            # that is not evidence that the pane is gone.
            if server_panes is not None and tty not in server_panes:
                archive(item, "pane-gone", known_panes=sorted(server_panes))
                continue

        elif (
            tty
            and switch_source
            and not _check_pane_exists(tty, switch_source, sockets.get(channel))
        ):
            archive(item, "pane-gone")
            continue

        remaining.append(item)

    # Second pass: group by TTY and handle duplicates/process exit
    tty_groups: dict[
        tuple[str, str],
        list[tuple[str, str, str, float, bool, str | None, str, str | None]],
    ] = {}

    for (
        channel,
        _session_id,
        _cwd,
        created_at,
        _is_unread,
        tty,
        _db_message,
        _switch_source,
    ) in remaining:
        if not tty:
            # Every check here keys on the tty, so a row without one is never
            # archived automatically - it survives any number of session kills.
            # Logged once, because that presents as the archiver being broken
            # rather than as a field being absent.
            if channel not in _warned_no_tty:
                _warned_no_tty.add(channel)
                _log.warning("%s has no tty recorded; cannot auto-archive it", channel)
            continue

        if channel.startswith("claude:"):
            process_name = "claude"
        elif channel.startswith("openclaw:"):
            process_name = "openclaw"
        elif channel.startswith("opencode:"):
            process_name = "opencode"
        else:
            process_name = "codex"
        key = (tty, process_name)

        if key not in tty_groups:
            tty_groups[key] = []
        tty_groups[key].append(
            (
                channel,
                _session_id,
                _cwd,
                created_at,
                _is_unread,
                tty,
                _db_message,
                _switch_source,
            )
        )

    # Process each TTY group
    for (tty, process_name), sessions in tty_groups.items():
        if len(sessions) == 1:
            # Only one session - check if process is still running
            if not is_process_running_on_tty(tty, process_name):
                archive(sessions[0], "process-exited", expected_process=process_name)
        else:
            # Multiple sessions on same TTY - keep newest, archive rest
            # Sort by created_at descending (newest first)
            sessions.sort(key=lambda x: x[3], reverse=True)
            newest = sessions[0]
            newest_channel = newest[0]

            # Check if process is running
            process_running = is_process_running_on_tty(tty, process_name)

            for item in sessions[1:]:  # Skip newest
                archive(item, "newer-session-on-tty", replacement=newest_channel)

            # If process isn't running, also archive the newest
            if not process_running:
                archive(newest, "process-exited", expected_process=process_name)

    return archived


def unified_watch_loop(
    backends: list[WatcherBackend],
    get_active: Callable[[], list[tuple[str, str, str, float, bool, str | None, str, str | None]]],
    mark_read: Callable[[str], int],
    update_message: Callable[[str, str], int],
    archive_channel: Callable[[str], None] | None = None,
    mark_unread: Callable[[str], int] | None = None,
    record_location: Callable[[str, str, str, str | None], None] | None = None,
    record_model: Callable[[str, str, str], None] | None = None,
    models: Callable[[], dict[str, ModelInfo]] | None = None,
    sockets: Callable[[], dict[str, str]] | None = None,
    poll_interval: float = 2.0,
    stop_event: threading.Event | None = None,
) -> None:
    """Main watch loop - polls all active sessions across all backends.

    Args:
        backends: List of watcher backends (claude, codex, etc.)
        get_active: Callback returning list of (channel, session_id, cwd, created_at, is_unread, tty, db_message, switch_source)
        mark_read: Callback to mark a channel as read
        update_message: Callback to update message for a channel
        archive_channel: Optional callback to archive a channel when session exits
        mark_unread: Optional callback to mark a channel as needing attention (for backends like OpenClaw)
        record_location: Optional callback to note a channel's (tmux_session, tmux_window, tmux_socket)
        record_model: Optional callback to note a channel's (provider, model)
        models: Optional callback returning the models currently saved by channel
        sockets: Optional callback returning channel -> recorded tmux socket
        poll_interval: How often to poll (seconds)
    """
    # Build prefix -> backend mapping
    backend_map = {b.CHANNEL_PREFIX: b for b in backends}
    _log.info("watcher started with backends: %s", list(backend_map.keys()))

    # Track last observed transcript timestamp per channel (as unix float)
    # Used to detect genuinely new activity vs polling same state
    last_observed_ts: dict[str, float] = {}
    # Track last "needs attention" timestamp per channel to avoid re-marking
    last_attention_ts: dict[str, float] = {}
    last_observed_model: dict[str, ModelInfo] = {}
    initial_model_checked: set[str] = set()
    # Successful transcript lookups are stable. Missing paths are retried: a
    # session hook commonly arrives just before the backend creates its file.
    session_cache: dict[str, Path] = {}
    session_retry_after: dict[str, float] = {}

    while stop_event is None or not stop_event.is_set():
        try:
            active = get_active()
            # Which tmux server each session was recorded on. Read once per poll:
            # both the location pass and the archiver need it, and it is one
            # query rather than one per row.
            by_channel = sockets() if sockets else {}
            saved_models = models() if models else {}

            # One tmux listing per server, shared by both location recording
            # and stale-session archiving. Before this, each pass ran its own
            # `tmux list-panes -a` per server, and the archiver ran one per
            # *session* - N+1 subprocesses every 0.5s.
            servers = _tmux_servers_needed(active, by_channel)
            pane_locations = _fetch_pane_locations(servers)

            if record_location:
                _record_locations(active, record_location, by_channel, pane_locations)

            # Archive stale sessions: group by TTY and keep only the newest per TTY
            if archive_channel:
                archived_channels = _archive_stale_sessions(
                    active,
                    archive_channel,
                    by_channel,
                    pane_locations,
                )
                # Remove archived channels from active list
                active = [s for s in active if s[0] not in archived_channels]
                # Clean up caches for archived channels
                for channel in archived_channels:
                    last_observed_ts.pop(channel, None)
                    last_observed_model.pop(channel, None)
                    initial_model_checked.discard(channel)
                    to_remove = [k for k in session_cache if k.startswith(f"{channel}:")]
                    for k in to_remove:
                        session_cache.pop(k, None)
                    retry_to_remove = [
                        k for k in session_retry_after if k.startswith(f"{channel}:")
                    ]
                    for k in retry_to_remove:
                        session_retry_after.pop(k, None)

            for (
                channel,
                session_id,
                cwd,
                created_at,
                is_unread,
                _tty,
                _db_message,
                _switch_source,
            ) in active:
                # Find the right backend for this channel
                backend = None
                for prefix, b in backend_map.items():
                    if channel.startswith(prefix):
                        backend = b
                        break

                if not backend:
                    continue

                # Resolve reader: backends can override for remote reading (e.g., SSH)
                read_fn = getattr(backend, "read_lines", read_jsonl_tail)

                cache_key = f"{channel}:{session_id}"
                session_path = session_cache.get(cache_key)
                if session_path is None:
                    now = time.monotonic()
                    if now < session_retry_after.get(cache_key, 0.0):
                        continue
                    session_path = backend.get_session_path(session_id, cwd)
                    if session_path is None:
                        session_retry_after[cache_key] = (
                            now + _MISSING_SESSION_RETRY_SECONDS
                        )
                        continue
                    session_cache[cache_key] = session_path
                    session_retry_after.pop(cache_key, None)

                # Read the tail once and parse it once. The three consumers
                # below each traversed the same 50 lines independently;
                # with 60+ sessions that tripled the JSON work per tick.
                lines = read_fn(session_path)
                recent: list[dict] = []
                for line in reversed(lines[-50:]):
                    try:
                        recent.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

                if record_model and (get_model := getattr(backend, "get_model", None)):
                    model = _latest_model(recent, get_model)
                    model = model or last_observed_model.get(channel)
                    if model is None and channel not in initial_model_checked:
                        get_initial_model = getattr(backend, "get_initial_model", None)
                        model = get_initial_model(session_path) if get_initial_model else None
                        initial_model_checked.add(channel)
                    if model:
                        last_observed_model[channel] = model
                        if model != saved_models.get(channel):
                            record_model(channel, model.provider, model.model)
                            saved_models[channel] = model
                            _log.info(
                                "recorded model for %s: %s/%s",
                                channel,
                                model.provider,
                                model.model,
                            )

                # For unread notifications, check if we should mark as read
                if is_unread:
                    for entry in recent:
                        ts = parse_timestamp(entry.get("timestamp", ""))
                        if ts and ts > created_at and backend.should_dismiss(entry):
                            mark_read(channel)
                            _log.info(
                                "marked read: %s (trigger: %s at %s)",
                                channel,
                                entry.get("type", "?"),
                                entry.get("timestamp", "")[:19],
                            )
                            break

                # For read notifications, check if agent now needs attention
                if not is_unread and mark_unread:
                    needs_attention_fn = getattr(backend, "needs_attention", None)
                    if needs_attention_fn:
                        since_ts = last_attention_ts.get(channel, created_at)
                        for entry in recent:
                            ts = parse_timestamp(entry.get("timestamp", ""))
                            if ts and ts > since_ts and needs_attention_fn(entry):
                                last_attention_ts[channel] = ts
                                mark_unread(channel)
                                _log.info(
                                    "marked unread: %s (agent waiting at %s)",
                                    channel,
                                    entry.get("timestamp", "")[:19],
                                )
                                break

                # Update message from transcript
                for entry in recent:
                    activity = backend.describe_activity(entry)
                    if activity:
                        entry_ts = parse_timestamp(entry.get("timestamp", ""))
                        if entry_ts and entry_ts != last_observed_ts.get(channel):
                            update_message(channel, activity)
                            last_observed_ts[channel] = entry_ts
                            _log.info("updated %s: %s", channel, activity)
                        break

        except Exception as e:
            _log.error("error: %s", e, exc_info=True)

        if stop_event is None:
            time.sleep(poll_interval)
        else:
            stop_event.wait(poll_interval)


_watcher_thread: threading.Thread | None = None
_watcher_stop: threading.Event | None = None


def start_unified_watcher(
    backends: list[WatcherBackend],
    get_active: Callable[[], list[tuple[str, str, str, float, bool, str | None, str, str | None]]],
    mark_read: Callable[[str], int],
    update_message: Callable[[str, str], int],
    archive_channel: Callable[[str], None] | None = None,
    mark_unread: Callable[[str], int] | None = None,
    record_location: Callable[[str, str, str, str | None], None] | None = None,
    record_model: Callable[[str, str, str], None] | None = None,
    models: Callable[[], dict[str, ModelInfo]] | None = None,
    sockets: Callable[[], dict[str, str]] | None = None,
) -> None:
    """Start the unified session watcher daemon thread.

    Args:
        backends: List of watcher backends to monitor
        get_active: Callback returning list of (channel, session_id, cwd, created_at, is_unread, tty, db_message, switch_source)
        mark_read: Callback to mark a channel as read
        update_message: Callback to update message for a channel
        archive_channel: Optional callback to archive a channel when session exits
        mark_unread: Optional callback to mark a channel as needing attention
        record_location: Optional callback to note a channel's (tmux_session, tmux_window, tmux_socket)
        record_model: Optional callback to note a channel's (provider, model)
        models: Optional callback returning the models currently saved by channel
        sockets: Optional callback returning channel -> recorded tmux socket
    """
    global _watcher_stop, _watcher_thread

    if _watcher_thread is not None and _watcher_thread.is_alive():
        return  # Already running

    _watcher_stop = threading.Event()
    _watcher_thread = threading.Thread(
        target=unified_watch_loop,
        args=(backends, get_active, mark_read, update_message),
        kwargs={
            "archive_channel": archive_channel,
            "mark_unread": mark_unread,
            "record_location": record_location,
            "record_model": record_model,
            "models": models,
            "sockets": sockets,
            "stop_event": _watcher_stop,
        },
        daemon=True,
    )
    _watcher_thread.start()


def stop_unified_watcher(timeout: float = 2.0) -> None:
    """Stop and join the process-wide watcher thread, if one is running."""
    global _watcher_stop, _watcher_thread

    thread = _watcher_thread
    if thread is None:
        return

    if _watcher_stop is not None:
        _watcher_stop.set()
    thread.join(timeout)
    if thread.is_alive():
        _log.warning("watcher did not stop within %.1fs", timeout)
        return

    _watcher_thread = None
    _watcher_stop = None
    _log.info("watcher stopped")
