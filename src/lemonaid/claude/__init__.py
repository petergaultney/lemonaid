"""Lemonaid Claude Code integration."""

from pathlib import Path


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
