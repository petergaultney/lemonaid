"""`lemonaid watch --self --status`: whether a watcher runs, and how batches reach the lemon."""

import os

from . import codex_scout, push_path, push_scout, wait_state


def report(lemon_id: str, channel: str, thread: str) -> int:
    """0 when a watcher runs."""
    running = wait_state.is_armed(lemon_id)
    lines = [
        ("push scout running" if push_scout.running(lemon_id) else "watcher running")
        if running
        else "no watcher running"
    ]
    if channel.startswith("claude:"):
        found = push_path.gather(lemon_id, channel.removeprefix("claude:"))
        lines.insert(0 if push_path.path_of(found).loud else 1, push_path.status_line(found))
    elif channel.startswith("codex:"):
        own = thread or os.environ.get("CODEX_THREAD_ID", "") or channel.removeprefix("codex:")
        lines.append(codex_scout.status_line(own))
    print("\n".join(lines))
    return 0 if running else 1
