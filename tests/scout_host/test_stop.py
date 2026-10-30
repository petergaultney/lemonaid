"""Stopping one hosted scout removes its registration; the host is never signalled."""

import os
import threading

import pytest

from lemonaid.watch import deaf_waiter, registry, scout_roster, stopping, wait_state, waiter_lock

from .shared import hosting

_LEMON = "task.IndexElf"


def _serving() -> threading.Timer:
    """The test process holds the lemon's lock as the host's scout thread would, until stopped."""
    scout_roster.register(_LEMON, "claude:abcd1234", "", "/work")
    path = wait_state.lock_path(_LEMON)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = waiter_lock.acquire(path)
    assert lock is not None

    def release() -> None:
        if scout_roster.read(_LEMON) is None:
            lock.close()
        else:
            threading.Timer(0.05, release).start()

    timer = threading.Timer(0.05, release)
    timer.start()
    return timer


@pytest.fixture(autouse=True)
def _no_signals(monkeypatch):
    monkeypatch.setattr(os, "kill", lambda pid, sig: pytest.fail(f"signalled pid {pid}"))


def test_a_hosted_scout_is_listed_under_its_lemon_with_the_host_pid():
    with hosting():
        _serving()
        [waiter] = registry.mine("claude:abcd1234", "wait")

        assert waiter.hosted and waiter.pid == os.getpid() and waiter.targets == (_LEMON,)
        assert "--push" in waiter.command.split()
        scout_roster.remove(_LEMON)


def test_stopping_a_hosted_scout_removes_its_registration_and_waits_for_its_lock():
    with hosting():
        _serving()
        [waiter] = registry.mine("claude:abcd1234", "wait")

        stopping.stop(waiter, "claude:other")

        assert scout_roster.read(_LEMON) is None
        assert not waiter_lock.held(wait_state.lock_path(_LEMON))


def test_a_deaf_hosted_scout_is_never_killed(monkeypatch):
    with hosting():
        _serving()
        monkeypatch.setattr(wait_state, "deaf", lambda lemon_id: True)
        monkeypatch.setattr(stopping, "_HOSTED_GRACE", 0)
        monkeypatch.setattr(stopping, "_wait_for_exit", _timeout)

        deaf_waiter.clear(_LEMON, "claude:abcd1234")

        assert scout_roster.read(_LEMON) is None


def _timeout(waiter, grace):
    raise TimeoutError("did not exit")
