"""Per-actor watch lists, and the list waiter that serves one."""

import threading
import time

import pytest

from lemonaid.watch import doc_wait, watch_list

_ASK = '{{authorId="1" author="Peter">>is this true?<<}}'


@pytest.fixture
def list_path(tmp_path):
    return tmp_path / "lists" / "actor.json"


def test_adding_a_doc_asks_for_a_waiter_only_when_none_holds_the_list(tmp_path, list_path):
    doc = tmp_path / "a.md"
    doc.write_text("")

    assert watch_list.add(list_path, doc) is True
    held = watch_list.hold_waiter(list_path)
    assert held is not None
    assert watch_list.add(list_path, doc) is False
    assert watch_list.hold_waiter(list_path) is None
    held.close()


def test_remove_expire_and_touch(tmp_path, list_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    watch_list.add(list_path, a)
    watch_list.add(list_path, b)

    assert watch_list.remove(list_path, a) is True
    assert watch_list.remove(list_path, a) is False
    assert watch_list.expire(list_path, idle_seconds=3600) == []
    time.sleep(0.02)
    assert watch_list.expire(list_path, idle_seconds=0.01) == [str(b.resolve())]
    watch_list.touch(list_path, b)  # a removed doc stays removed
    assert watch_list.read(list_path) == {}


def test_the_list_waiter_delivers_touches_and_exits_once_its_list_is_empty(tmp_path, list_path):
    doc = tmp_path / "a.md"
    doc.write_text(f"A claim.{_ASK}\n")
    watch_list.add(list_path, doc)
    waiter = watch_list.hold_waiter(list_path)
    assert waiter is not None
    sent: list[str] = []

    def deliver(message: str) -> None:
        sent.append(message)
        watch_list.remove(list_path, doc)

    thread = threading.Thread(
        target=doc_wait.wait_list,
        args=(tmp_path / "state", list_path, waiter, "Meyer", [], False, 45.0, deliver, 0.0, 0.01),
    )
    thread.start()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert len(sent) == 1
    assert "is this true?" in sent[0]
    assert watch_list.read(list_path) == {}
    assert watch_list.hold_waiter(list_path) is not None  # released on exit
