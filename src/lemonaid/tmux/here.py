"""The pane or session a lemonaid command was run from, as a tmux target.

With no -t and no pane of its own, tmux resolves "current" to the session with
the newest activity. That is the session whose key ran a `run-shell` binding
only until something else is newer: another process creating or attaching a
session in the moment before lemonaid asks. The toggle then read that
session's window as here and joined the scratch pane into it.

A `run-shell` job has no TMUX_PANE, but tmux sets TMUX to
`<socket>,<server pid>,<session id>` for the session that ran it.
"""

import os


def target() -> list[str]:
    """`-t` arguments naming the invoking pane, else its session; empty outside tmux."""
    if pane := os.environ.get("TMUX_PANE"):
        return ["-t", pane]

    fields = os.environ.get("TMUX", "").split(",")
    if len(fields) == 3 and fields[2].isdigit():
        return ["-t", f"${fields[2]}"]

    return []
