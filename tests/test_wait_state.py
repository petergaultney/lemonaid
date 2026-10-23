"""A unified waiter counts as armed only while it keeps polling."""

import os
import time

from lemonaid.messages import store, waiter
from lemonaid.watch import wait_state, waiter_lock

_LEMON = "task.IndexElf"


def _age(lemon_id: str, seconds: float) -> None:
    then = time.time() - seconds
    for path in wait_state.lock_path(lemon_id).parent.glob("wait.*"):
        os.utime(path, (then, then))


def test_a_waiter_that_stops_polling_is_deaf_until_it_beats_again():
    lock = wait_state.lock_path(_LEMON)
    lock.parent.mkdir(parents=True)
    inbox = store.inbox_for_id(_LEMON)
    with waiter_lock.acquire(lock), waiter.armed(inbox):
        assert wait_state.is_armed(_LEMON) and not wait_state.deaf(_LEMON)

        _age(_LEMON, wait_state.STALE + 1)
        assert wait_state.deaf(_LEMON)
        assert not wait_state.is_armed(_LEMON)
        assert not waiter.is_armed(inbox)

        wait_state.beat(_LEMON)
        assert wait_state.is_armed(_LEMON) and waiter.is_armed(inbox)


def test_a_silent_lemon_with_no_waiter_is_not_deaf():
    lock = wait_state.lock_path(_LEMON)
    lock.parent.mkdir(parents=True)
    waiter_lock.acquire(lock).close()
    _age(_LEMON, wait_state.STALE + 1)

    assert not wait_state.deaf(_LEMON)
