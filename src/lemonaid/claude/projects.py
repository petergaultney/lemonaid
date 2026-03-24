"""Claude Code project directory resolution.

Claude stores sessions under ~/.claude/projects/<encoded-path>/, where
the path is derived from the working directory at launch time. This module
handles the encoding, lookup, and history-based resolution.
"""

import json
from pathlib import Path

from ..log import get_logger

_log = get_logger("claude.projects")

_HISTORY_PATH = Path.home() / ".claude" / "history.jsonl"


def cwd_to_project_dir(cwd: str) -> str:
    """Convert a cwd path to Claude's project directory format.

    /Users/peter.gaultney/play/lemonaid -> -Users-peter-gaultney-play-lemonaid

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
    """Look up the project directory for a session via ~/.claude/history.jsonl.

    Returns the project path string, or None if not found.
    Multiple history entries may exist per session; we take the last one.
    """
    if not _HISTORY_PATH.exists():
        _log.warning("history.jsonl not found at %s", _HISTORY_PATH)
        return None

    project = None
    try:
        with open(_HISTORY_PATH) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("sessionId") == session_id:
                    project = entry.get("project")
    except OSError as e:
        _log.warning("failed to read history.jsonl: %s", e)

    return project
