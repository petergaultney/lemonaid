"""Telling open pages when the grove changes: a change counts only when what the page draws
differs, and each stream writes one event per change until its page goes away."""

import threading

import pytest

from lemonaid.grove.web import changes


def test_only_a_different_grove_counts_as_a_change():
    seen = changes.Changes()
    seen.saw({"blocks": [1]})
    seen.saw({"blocks": [1]})
    seen.saw({"blocks": [2]})

    assert seen.after(0, 0) == 2


class _Gone(Exception):
    pass


def test_a_stream_writes_each_change_and_heartbeats_until_its_page_is_gone():
    seen, written = changes.Changes(), []
    seen.saw({"blocks": []})

    def write(event: bytes) -> None:
        written.append(event)
        if len(written) == 2:
            threading.Timer(0.05, seen.saw, [{"blocks": [1]}]).start()
        if len(written) == 4:
            raise _Gone

    with pytest.raises(_Gone):
        changes.stream(seen, write, lambda: False, heartbeat=0.2, check=0.1)

    assert written == [b"retry: 1000\n\n", b": still here\n\n", b"data: 2\n\n", b": still here\n\n"]


def test_a_stream_ends_when_its_page_hangs_up():
    seen, checks = changes.Changes(), []

    changes.stream(
        seen, lambda event: None, lambda: checks.append(1) or len(checks) > 2, check=0.01
    )

    assert len(checks) == 3


def test_a_client_gets_a_few_streams_and_its_others_poll():
    seen = changes.Changes()
    with seen.admitted("tab") as first, seen.admitted("tab") as second:
        with seen.admitted("tab") as third, seen.admitted("phone") as elsewhere:
            assert (first, second, third, elsewhere) == (True, True, False, True)

        with seen.admitted("tab") as still:
            assert not still

    with seen.admitted("tab") as later:
        assert later


def test_watching_writes_each_change_of_a_mark_until_the_page_is_gone():
    marks, written = iter(["a", "a", "b", "b", "c"]), []

    changes.watch(lambda: next(marks), written.append, lambda: len(written) > 2, check=0.01)

    assert written == [b"retry: 1000\n\n", b"data: 1\n\n", b"data: 2\n\n"]
