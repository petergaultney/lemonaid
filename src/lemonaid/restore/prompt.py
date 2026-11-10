"""What a restored lemon is told: rearm the waiters its brief lists, and what died with its terminal.

A resumed harness comes back with none of its background tasks. A lemon whose push
scout runs gets its subscriptions back without being told; one that can't be pushed
to is prompted to rearm them. Prompts are typed into the composer, so each is one line.
"""

import time
from pathlib import Path

from ..brief import status, waiters
from ..messages import mailbox_command
from ..watch import command_record


def rearm(brief: Path, text: str, harness: str) -> str:
    """The prompt for a lemon whose brief at *brief* reads *text*, or "" when it lists nothing.

    A Codex lemon has no mailbox waiter to rearm: lemonaid queues its messages into
    the thread.
    """
    commands = [
        command
        for command in waiters.commands(text)
        if harness != "codex" or not mailbox_command.runs_watch(command)
    ]
    if not commands:
        return ""

    return " ".join(
        [
            "lemonaid restore resumed this session after its terminal went away, and every "
            f"background task it had is gone. Rearm the waiters your brief ({brief}) lists "
            "under ## Waiters, the way you first armed them:",
            ", ".join(f"`{command}`" for command in commands) + ".",
            "Then carry on where you left off, or end your turn with (quiet) if nothing is waiting.",
        ]
    )


def interrupted(lemon_id: str, text: str) -> bool:
    """Whether the lemon was running processes that died with its terminal: its brief's
    Status is `running`, or a `lemonaid run` it started was killed before it finished."""
    if status.split(text).status == "running":
        return True

    for path in command_record.directory().glob("*.json"):
        found = command_record.read(int(path.stem)) if path.stem.isdigit() else None
        if (
            found is not None
            and found.lemon == lemon_id
            and found.exit is None
            and not command_record.process_start(found.pid)
        ):
            return True
    return False


def lost_terminal(at: float) -> str:
    """The note for a lemon that `interrupted` says had processes running."""
    return (
        f"Your terminal was lost at {time.strftime('%H:%M', time.localtime(at))}. "
        "Every process started from this machine before then is gone, including commands "
        "run with `lemonaid run` and anything your brief's Status said was running. "
        "Check what you started and start again what still needs to run."
    )
