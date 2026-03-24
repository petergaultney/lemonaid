"""Claude Code session resumption with project directory resolution.

Claude's --resume only searches the project dir matching the current cwd.
This module looks up the correct project directory from ~/.claude/history.jsonl
so resume works from any directory.
"""

import os
import sys

from .projects import find_session_project


def _resolve_project_dir(session_id: str) -> str:
    """Look up project dir for a session ID, or exit with an error."""
    project = find_session_project(session_id)
    if not project:
        print(f"Session {session_id} not found in Claude history", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(project):
        print(f"Project directory no longer exists: {project}", file=sys.stderr)
        sys.exit(1)

    return project


def resume_session(session_id: str) -> None:
    """cd to the correct project directory and exec claude --resume."""
    project = _resolve_project_dir(session_id)
    os.chdir(project)
    os.execvp("claude", ["claude", "--resume", session_id])


def forward_to_claude(claude_args: list[str]) -> None:
    """Forward args to claude, resolving --resume to the correct project dir.

    If --resume is among the args, looks up the project directory and cd's
    there before exec'ing. Other args are passed through verbatim.
    """
    for i, arg in enumerate(claude_args):
        if arg == "--resume" and i + 1 < len(claude_args):
            project = _resolve_project_dir(claude_args[i + 1])
            os.chdir(project)
            break

    os.execvp("claude", ["claude", *claude_args])


def maybe_intercept(argv: list[str]) -> bool:
    """Intercept `lemonaid claude <flags>` and forward to the real claude CLI.

    Returns True if intercepted (never actually returns — execs claude).
    Returns False if this isn't a forwarding case.

    Args:
        argv: sys.argv[1:] from the main entry point
    """
    if (
        len(argv) >= 2
        and argv[0] == "claude"
        and argv[1].startswith("-")
        and argv[1] not in ("-h", "--help")
    ):
        forward_to_claude(argv[1:])

    return False
