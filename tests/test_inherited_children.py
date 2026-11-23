"""A process reaps the children it keeps across `exec`."""

import subprocess
import sys

_OLD_CODE = """
import os, subprocess, sys, time
running, done = subprocess.Popen(["sleep", "1"]), subprocess.Popen(["true"])
time.sleep(0.3)
os.execv(sys.executable, [sys.executable, "-c", sys.argv[1]])
"""

_NEW_CODE = """
import os, time
from lemonaid import process_table
from lemonaid.watch import inherited_children

def kept():
    return [
        stat
        for ppid, stat, command in process_table.listing("ppid", "stat", "comm", timeout=5)
        if int(ppid) == os.getpid() and os.path.basename(command) != "ps"
    ]

before = len(kept())
inherited_children.reap()
zombies = sum(stat.startswith("Z") for stat in kept())
deadline = time.monotonic() + 10
while kept() and time.monotonic() < deadline:
    time.sleep(0.05)
print(before, zombies, len(kept()))
"""


def test_restarted_code_reaps_finished_children_while_another_still_runs():
    result = subprocess.run(
        [sys.executable, "-c", _OLD_CODE, _NEW_CODE], capture_output=True, text=True, timeout=30
    )

    assert result.stdout.split() == ["2", "0", "0"], result.stderr
