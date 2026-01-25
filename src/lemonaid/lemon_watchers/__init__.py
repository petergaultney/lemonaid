"""Shared utilities and unified watcher for LLM session monitoring."""

from .common import (
    detect_terminal_switch_source,
    get_name_from_cwd,
    get_tmux_session_name,
    get_tty,
    short_filename,
    shorten_path,
)
from .watcher import (
    WatcherBackend,
    get_latest_activity,
    has_activity_since,
    parse_timestamp,
    read_jsonl_tail,
    start_unified_watcher,
)

__all__ = [
    "WatcherBackend",
    "detect_terminal_switch_source",
    "get_latest_activity",
    "get_name_from_cwd",
    "get_tmux_session_name",
    "get_tty",
    "has_activity_since",
    "parse_timestamp",
    "read_jsonl_tail",
    "short_filename",
    "shorten_path",
    "start_unified_watcher",
]
