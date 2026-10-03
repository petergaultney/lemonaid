"""The prompt a restored lemon starts with: rearm the waiters its brief lists.

A resumed harness comes back with none of its background tasks, and a Claude
without its inbox waiter can't be told so by message. Starting it with a prompt
is the one way to wake it that doesn't depend on something it has to arm first.
"""

from pathlib import Path

from ..brief import waiters

_INBOX_WAITER = "lemonaid inbox watch"


def rearm(brief: Path, text: str, harness: str) -> str:
    """The prompt for a lemon whose brief at *brief* reads *text*, or "" when it lists nothing.

    A Codex lemon has no inbox waiter to rearm: lemonaid queues its messages into
    the thread.
    """
    commands = [
        command
        for command in waiters.commands(text)
        if harness != "codex" or _INBOX_WAITER not in command
    ]
    if not commands:
        return ""

    return "\n".join(
        [
            "lemonaid restore resumed this session after its terminal went away, and every "
            f"background task it had is gone. Rearm the waiters your brief ({brief}) lists "
            "under ## Waiters, the way you first armed them:",
            "",
            *(f"- `{command}`" for command in commands),
            "",
            "Then carry on where you left off, or end your turn with (quiet) if nothing is waiting.",
        ]
    )
