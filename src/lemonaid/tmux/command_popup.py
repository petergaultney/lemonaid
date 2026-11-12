"""A popup over the calling client that runs one command and closes when it exits."""

import os
import subprocess
from collections import abc


def open_popup(command: abc.Sequence[str], title: str) -> None:
    """Run *command* in a popup sized to most of the window. Returns without waiting for it.

    A popup inherits the tmux server's environment rather than the caller's, so
    lemonaid's own variables (a sandbox's database, briefs and state) are passed on.
    """
    passed = [
        arg
        for name, value in os.environ.items()
        if name.startswith("LEMONAID_")
        for arg in ("-e", f"{name}={value}")
    ]
    subprocess.Popen(
        [
            "tmux",
            "display-popup",
            "-E",
            "-w",
            "90%",
            "-h",
            "90%",
            *passed,
            "-T",
            # -T is a format, where a bare # starts a variable.
            f" {title.replace('#', '##')} ",
            *command,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
