"""A popup over the calling client that runs one command and closes when it exits."""

import shutil
import subprocess
import tempfile
from collections import abc
from pathlib import Path

from ..log import get_logger

_log = get_logger("tmux.command_popup")

# Runs the command, then records its exit status in the file named first.
_RECORDING = 'status_file=$1; shift; "$@"; echo $? > "$status_file"'


def run(command: abc.Sequence[str], title: str) -> int | None:
    """Run *command* in a popup sized to most of the window, wait for it to close, and return
    its exit status; None when the popup never ran it (no client, or a tmux without popups).

    The status comes from a file the command's wrapper writes, not from `display-popup`'s own
    exit, which is also nonzero when the popup can't open. It blocks; call it from a worker.
    """
    folder = Path(tempfile.mkdtemp(prefix="lemonaid-popup-"))
    status_file = folder / "status"
    try:
        done = subprocess.run(
            [
                "tmux",
                "display-popup",
                "-E",
                "-w",
                "90%",
                "-h",
                "90%",
                "-T",
                # -T is a format, where a bare # starts a variable.
                f" {title.replace('#', '##')} ",
                "sh",
                "-c",
                _RECORDING,
                "sh",
                str(status_file),
                *command,
            ],
            capture_output=True,
            text=True,
        )
        try:
            return int(status_file.read_text())
        except (OSError, ValueError):
            _log.warning("popup %r didn't run its command: %s", title, done.stderr.strip())
            return None
    finally:
        shutil.rmtree(folder, ignore_errors=True)
