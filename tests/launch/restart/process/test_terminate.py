import dataclasses
import os
import subprocess
import sys

import pytest

from lemonaid.launch.restart import process


def test_sigterm_only_exact_child_generation():
    child = subprocess.Popen(["sleep", "30"])
    other = subprocess.Popen(["sleep", "30"])
    try:
        identity = process.inspect(child.pid)
        assert identity is not None
        with pytest.raises(ValueError, match="generation changed"):
            process.terminate(dataclasses.replace(identity, started="reused PID"))
        assert child.poll() is None
        process.terminate(identity)
        assert child.wait(timeout=3) == -15
        assert other.poll() is None
    finally:
        for owned in (child, other):
            if owned.poll() is None:
                owned.terminate()
            owned.wait(timeout=3)


def test_sigterm_timeout_never_escalates_to_sigkill():
    child = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(30)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline() == "ready\n"
        identity = process.inspect(child.pid)
        assert identity is not None
        with pytest.raises(TimeoutError, match="no replacement"):
            process.terminate(identity, timeout=0.1)
        assert child.poll() is None
    finally:
        child.kill()
        child.wait(timeout=3)
        child.stdout.close()


def test_inventory_includes_a_child_without_the_controlling_terminal():
    child = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        found = {entry.pid: entry for entry in process.descendants(os.getpid())}
        assert child.pid in found
        assert found[child.pid].tty in ("??", "?")
    finally:
        child.terminate()
        child.wait(timeout=3)
