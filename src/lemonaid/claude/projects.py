"""Claude Code project directory resolution.

Claude stores sessions under ~/.claude/projects/<encoded-path>/, where
the path is derived from the working directory at launch time. This module
handles the encoding, lookup, and history-based resolution.
"""

import dataclasses
import json
import threading
from pathlib import Path

from ..log import get_logger

_log = get_logger("claude.projects")

_HISTORY_PATH = Path.home() / ".claude" / "history.jsonl"


def cwd_to_project_dir(cwd: str) -> str:
    """Convert a cwd path to Claude's project directory format.

    /Users/first.last/play/lemonaid -> -Users-first-last-play-lemonaid

    Claude replaces / and . with - in the directory name.
    """
    project_dir = cwd.replace("/", "-").replace(".", "-")
    if project_dir.startswith("-"):
        project_dir = project_dir[1:]
    return "-" + project_dir


def get_project_path(cwd: str) -> Path:
    """Get the Claude project directory path for a given cwd."""
    return Path.home() / ".claude" / "projects" / cwd_to_project_dir(cwd)


def find_project_path(cwd: str) -> Path | None:
    """Find the Claude project directory, trying parent paths as fallback.

    Claude sometimes uses a parent directory (like git root) instead of the
    exact cwd. This is common with git worktrees where Claude stores sessions
    under the main repo path rather than the worktree-specific path.

    Returns the first existing project directory found, or None.
    """
    projects_dir = Path.home() / ".claude" / "projects"
    path = Path(cwd)

    # Try cwd and each parent up to root
    for candidate in [path, *path.parents]:
        if candidate == Path("/"):
            break

        project_dir = projects_dir / cwd_to_project_dir(str(candidate))
        if project_dir.exists():
            return project_dir

    return None


def find_session_project(session_id: str) -> str | None:
    """Look up the project directory for a session.

    First tries ~/.claude/history.jsonl (fast, covers interactive sessions).
    Falls back to scanning ~/.claude/projects/*/<session_id>.jsonl — needed
    for sessions started by remote agents / scheduled triggers, which never
    log to history.jsonl.

    Returns the project path string, or None if not found.
    """
    from_history = _find_in_history(session_id)
    if from_history:
        return from_history

    return _find_in_projects(session_id)


@dataclasses.dataclass
class _HistoryIndex:
    """The project of each session in a history.jsonl, as of `offset` bytes into it."""

    projects: dict[str, str] = dataclasses.field(default_factory=dict)
    offset: int = 0
    file: tuple[Path, int] | None = None  # path and inode


# Claude only appends to history.jsonl, so the index reads each line once. A file
# that shrank or was replaced is read again from the start.
_history = _HistoryIndex()
_history_lock = threading.Lock()


def _read_history(index: _HistoryIndex, path: Path) -> None:
    stat = path.stat()
    if index.file != (path, stat.st_ino) or stat.st_size < index.offset:
        index.projects.clear()
        index.offset, index.file = 0, (path, stat.st_ino)
    if stat.st_size == index.offset:
        return

    with open(path, "rb") as f:
        f.seek(index.offset)
        data = f.read()
    complete = data[: data.rfind(b"\n") + 1]  # a line still being written waits for the next read
    for line in complete.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(entry, dict) and entry.get("sessionId") and entry.get("project"):
            index.projects[entry["sessionId"]] = entry["project"]
    index.offset += len(complete)


def _find_in_history(session_id: str) -> str | None:
    if not _HISTORY_PATH.exists():
        _log.warning("history.jsonl not found at %s", _HISTORY_PATH)
        return None

    with _history_lock:
        try:
            _read_history(_history, _HISTORY_PATH)
        except OSError as e:
            _log.warning("failed to read history.jsonl: %s", e)
        return _history.projects.get(session_id)


def _find_in_projects(session_id: str) -> str | None:
    """Scan ~/.claude/projects/*/<session_id>.jsonl and read cwd from the transcript.

    The directory name encoding (/ and . both collapse to -) is lossy, so we
    read the actual cwd from a transcript entry rather than trying to decode.
    """
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return None

    for transcript in projects_dir.glob(f"*/{session_id}.jsonl"):
        cwd = _read_cwd_from_transcript(transcript)
        if cwd:
            return cwd

    return None


def _read_cwd_from_transcript(transcript: Path) -> str | None:
    try:
        with open(transcript) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                cwd = entry.get("cwd")
                if cwd:
                    return cwd
    except OSError as e:
        _log.warning("failed to read transcript %s: %s", transcript, e)

    return None
