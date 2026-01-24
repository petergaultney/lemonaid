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
