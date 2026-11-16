import os
import threading

from lemonaid.messages import start_lock


def test_the_holder_of_a_start_lock_names_itself_until_it_lets_go(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "lemonaid.db"))
    assert start_lock.holder("claude:a") == ""

    with start_lock.held("claude:a"):
        assert start_lock.holder("claude:a").startswith(f"pid {os.getpid()}: ")
        assert start_lock.holder("claude:b") == ""

    assert start_lock.holder("claude:a") == ""


def test_a_start_waits_for_the_holder_and_then_takes_the_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "lemonaid.db"))
    taken, release, order = threading.Event(), threading.Event(), []

    def first() -> None:
        with start_lock.held("claude:a"):
            taken.set()
            release.wait(5)
            order.append("first")

    thread = threading.Thread(target=first)
    thread.start()
    taken.wait(5)
    threading.Timer(0.2, release.set).start()
    with start_lock.held("claude:a"):
        order.append("second")
    thread.join(5)

    assert order == ["first", "second"]
