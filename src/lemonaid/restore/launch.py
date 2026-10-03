"""The line a restored lemon is started with, whatever terminal it goes back into."""

import shlex
import typing as ty
from pathlib import Path

from ..config import Config
from ..inbox.db import Notification
from ..launch import command
from ..resume import build_resume_command

# The harnesses whose resume command takes a first prompt as its last argument.
_PROMPTABLE = frozenset({"claude", "codex"})


class Launch(ty.NamedTuple):
    cwd: str
    line: str
    environment: dict[str, str]  # for the shell the line is typed into
    prompted: bool  # whether the line starts the lemon on the prompt it was given


def launch(notification: Notification, config: Config, prompt: str) -> Launch | None:
    """How to resume *notification*'s session starting on *prompt*, or None if it can't be.

    Only Claude and Codex take a first prompt on resume; any other harness is
    resumed without one, and says so in `prompted`.

    The line is `lemon start`'s, so a Codex gets the same overrides that keep
    its trust and update dialogs from stopping it before it reads the prompt.
    """
    resumable = build_resume_command(config, notification.channel, notification.metadata)
    if resumable is None:
        return None

    cwd, argv = resumable
    prompted = bool(prompt) and notification.channel.partition(":")[0] in _PROMPTABLE
    line, environment = command.harness_line(
        shlex.join(argv), Path(cwd), prompt if prompted else ""
    )
    return Launch(cwd, line, environment, prompted)
