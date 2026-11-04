"""How mailbox commands are spelled, including the `lemonaid inbox` spellings older briefs use."""

import shlex
from collections import abc

COMMAND = "mailbox"
WATCH = ("lemonaid", COMMAND, "watch")
_LEGACY = "inbox"
_SUBCOMMANDS = ("next", "watch", "deliver")


def canonical(argv: abc.Sequence[str]) -> list[str]:
    """*argv* (after `lemonaid`) with `inbox next|watch|deliver` respelled as `mailbox`."""
    if len(argv) > 1 and argv[0] == _LEGACY and argv[1] in _SUBCOMMANDS:
        return [COMMAND, *argv[1:]]

    return list(argv)


def is_watch(words: abc.Sequence[str]) -> bool:
    """Whether *words* run `lemonaid mailbox watch`, in either spelling."""
    return list(words[:1]) == ["lemonaid"] and canonical(words[1:3]) == list(WATCH[1:])


def runs_watch(command: str) -> bool:
    """Whether the shell *command* runs `lemonaid mailbox watch`, in either spelling."""
    try:
        return is_watch(shlex.split(command))
    except ValueError:
        return False
