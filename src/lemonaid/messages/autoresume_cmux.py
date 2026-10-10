"""Bring back, through cmux, a lemon whose harness exited.

lemonaid has no way to type into a cmux surface, so an idle cmux lemon with
no waiter can't be prompted, only told about.
"""

import shlex
from pathlib import Path

from ..cmux import navigation
from ..config import Config
from ..inbox import db
from ..launch import command
from ..resume import build_resume_command
from . import autoresume_tmux


def start(row: db.Notification, config: Config, text: str = autoresume_tmux.PROMPT) -> str:
    """Resume *row*'s session on *text* in a new, unfocused workspace. Returns why not, or ""."""
    resumable = build_resume_command(config, row.channel, row.metadata)
    if resumable is None:
        return "no working directory or resume command is recorded for it"

    cwd, argv = resumable
    # With no prompt, the line carries only the flags that keep a Codex's startup
    # dialogs from stopping it; the prompt is one more word for cmux to quote.
    line, _ = command.harness_line(
        shlex.join(argv), Path(cwd), "", command.codex_writable_roots(config.tmux_session)
    )
    words = [*shlex.split(line), text]
    if not navigation.open_workspace(cwd, words, row.name or Path(cwd).name, focus=False):
        return "cmux could not open a workspace for it"

    return ""
