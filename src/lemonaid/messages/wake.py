"""What a resumed lemon is told, and how to resume it by hand; independent of the terminal."""

import shlex

from ..config import Config
from ..inbox import db
from ..resume import build_resume_command

PROMPT = (
    "You were resumed to read a message: run `lemonaid inbox next --self`. Then rearm "
    "the waiters your brief lists under ## Waiters, and carry on."
)


def resume_line(row: db.Notification, config: Config) -> str:
    """The shell line that resumes *row*'s session by hand, or ""."""
    resumable = build_resume_command(config, row.channel, row.metadata)
    if resumable is None:
        return ""

    cwd, argv = resumable
    return f"cd {shlex.quote(cwd)} && {shlex.join(argv)}"
