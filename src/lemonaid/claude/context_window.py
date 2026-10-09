"""Each Claude session's context window, which only its statusLine command is told.

The transcript records the tokens a request used but not the window they count
against, which differs by model and by plan.
"""

from pathlib import Path

from ..usage import paths


def _windows_dir() -> Path:
    return paths.usage_dir() / "claude-context-windows"


def save(statusline_data: dict) -> None:
    session_id = statusline_data.get("session_id")
    size = (statusline_data.get("context_window") or {}).get("context_window_size")
    if not isinstance(session_id, str) or not session_id or not isinstance(size, int) or size <= 0:
        return

    target = _windows_dir() / session_id
    if read(session_id) == size:
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(size))


def read(session_id: str) -> int:
    try:
        return int((_windows_dir() / session_id).read_text())
    except (OSError, ValueError):
        return 0
