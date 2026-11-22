import signal
import time

import pytest

from lemonaid.rules import search

_LONG = "a" * 10000 + "!"


def test_a_quick_search_returns_its_match():
    found = search.search(r"merge #\d+", "Merge #12? merge #13", 0.5)

    assert found is not None
    assert found.group(0) == "merge #13"


@pytest.mark.parametrize("regex", [r"(a|aa)+$", r"a*a*a*a*a*b", r"^(a+)+$"])
def test_a_backtracking_search_stops_at_its_limit(regex):
    started = time.monotonic()

    with pytest.raises(search.TooSlow):
        search.search(regex, _LONG, 0.05)

    assert time.monotonic() - started < 1


def test_no_time_left_is_too_slow_without_searching():
    with pytest.raises(search.TooSlow):
        search.search("a", "a", 0)


def test_the_previous_alarm_handler_and_timer_are_restored():
    def mine(signum, frame):
        pass

    previous = signal.signal(signal.SIGALRM, mine)
    try:
        search.search("a", "a", 0.5)
        with pytest.raises(search.TooSlow):
            search.search(r"(a|aa)+$", _LONG, 0.05)

        assert signal.getsignal(signal.SIGALRM) is mine
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    finally:
        signal.signal(signal.SIGALRM, previous)
