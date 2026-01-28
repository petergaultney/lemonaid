"""Path utilities for lemonaid."""

from pathlib import Path


def get_log_dir() -> Path:
    """Get the directory for lemonaid logs.

    Uses XDG state directory: ~/.local/state/lemonaid/logs/
    """
    log_dir = Path.home() / ".local" / "state" / "lemonaid" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_path(name: str) -> Path:
    """Get the path to a specific log file.

    Args:
        name: Log file name (e.g., "watcher", "claude-notify")

    Returns:
        Path to ~/.local/state/lemonaid/logs/{name}.log
    """
    return get_log_dir() / f"{name}.log"
