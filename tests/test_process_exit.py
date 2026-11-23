"""kqueue reports a process's exit whether or not anyone has reaped it."""

import select
import subprocess
import time

import pytest

from lemonaid.watch import process_exit

pytestmark = pytest.mark.skipif(not hasattr(select, "kqueue"), reason="kqueue only")


def test_an_exit_nobody_has_reaped_is_reported_and_stays_reported():
    child = subprocess.Popen(["sleep", "0.2"])
    exited = process_exit.watch(child.pid)
    assert exited is not None and not exited()

    deadline = time.monotonic() + 5
    while not exited() and time.monotonic() < deadline:
        time.sleep(0.02)

    assert exited()
    assert child.returncode is None  # not reaped
    child.wait()


def test_a_process_that_exited_before_it_was_watched_has_exited():
    child = subprocess.Popen(["true"])
    time.sleep(0.3)
    exited = process_exit.watch(child.pid)

    assert exited is not None and exited()
    child.wait()
