"""A native tool job remains test-owned even when it has its own terminal."""

import time
from pathlib import Path

from lemonaid.launch.restart import pane, process


def start_background_job(socket, target, source, completed, previous, harness):
    instruction = (
        "Start sleep 120 with the exec tool using yield_time_ms=1 so it returns a live session. "
        "Do not use & or detach/reparent it. Do not wait for completion. Reply BACKGROUND_READY."
        if harness == "codex"
        else "Use Bash with run_in_background=true to run sleep 120. Do not use & or detach/reparent "
        "it. Do not wait for completion. Reply BACKGROUND_READY."
    )
    pane.run(socket, "send-keys", "-t", target.pane, "-l", instruction)
    time.sleep(1)  # Native TUIs defer Enter while detecting pasted text.
    pane.run(socket, "send-keys", "-t", target.pane, "Enter")
    completed(previous)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        jobs = [
            entry
            for entry in process.descendants(source.pid)
            if Path(entry.executable).name == "sleep"
        ]
        if jobs:
            return jobs
        time.sleep(0.1)
    raise AssertionError("Native harness did not retain the requested test-owned background job")
