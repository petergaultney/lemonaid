"""Resume Claude conversations in their directory or a surviving parent."""

import os
import sys
from pathlib import Path

from ..resume_directory import surviving_directory
from .projects import find_session_project


def _resume_context(session_id: str) -> tuple[str, str]:
    project = find_session_project(session_id)
    if not project:
        print(f"Session {session_id} not found in Claude history", file=sys.stderr)
        sys.exit(1)

    if Path(project).is_dir():
        return project, session_id

    projects = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / "projects"
    transcripts = list(projects.glob(f"*/{session_id}.jsonl"))
    if len(transcripts) != 1:
        print(
            f"Cannot resume {session_id}: expected one saved transcript, found {len(transcripts)}",
            file=sys.stderr,
        )
        sys.exit(1)

    directory = surviving_directory(project)
    print(f"Original directory is gone: {project}. Resuming in {directory}.", file=sys.stderr)
    return directory, str(transcripts[0])


def resume_session(session_id: str, prompt: str = "") -> None:
    """cd to the correct project directory and exec claude --resume, starting on *prompt* if given."""
    project, target = _resume_context(session_id)
    os.chdir(project)
    os.execvp("claude", ["claude", "--resume", target, *([prompt] if prompt else [])])


def forward_to_claude(claude_args: list[str]) -> None:
    """Forward args to claude, resolving --resume to the correct project dir.

    If --resume is among the args, looks up the project directory and cd's
    there before exec'ing. Other args are passed through verbatim.
    """
    for i, arg in enumerate(claude_args):
        if arg == "--resume" and i + 1 < len(claude_args):
            project, target = _resume_context(claude_args[i + 1])
            claude_args = [*claude_args]
            claude_args[i + 1] = target
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
