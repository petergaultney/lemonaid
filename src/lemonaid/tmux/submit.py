"""Send a key to a running harness composer through tmux."""

import subprocess


def key_args(key: str) -> list[str]:
    if key == "C-Enter":
        return ["-H", "1b", "5b", "31", "33", "3b", "35", "75"]

    return [key]


def send(pane: str, key: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["tmux", "send-keys", "-t", pane, *key_args(key)], capture_output=True)
