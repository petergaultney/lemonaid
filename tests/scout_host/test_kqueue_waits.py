"""The kqueue hub wakes a loop when its file, directory or process changes, and only then."""

import os
import subprocess
import sys
import threading

import pytest

from lemonaid.watch import kqueue_waits

pytestmark = pytest.mark.skipif(not kqueue_waits.available(), reason="kqueue is macOS and BSD only")


@pytest.fixture
def hub() -> kqueue_waits.Hub:
    return kqueue_waits.Hub()


def _woken(wake: threading.Event, timeout: float = 2.0) -> bool:
    woken = wake.wait(timeout)
    wake.clear()
    return woken


def test_a_write_wakes_the_loop_watching_the_file(hub, tmp_path):
    path = tmp_path / "brief.md"
    path.write_text("one")
    wake = threading.Event()
    hub.watch([path], (), wake)
    assert not _woken(wake, 0.2)

    path.write_text("two")

    assert _woken(wake)


def test_a_file_replaced_by_rename_is_watched_again(hub, tmp_path):
    path = tmp_path / "review.md"
    path.write_text("one")
    wake = threading.Event()
    hub.watch([path], (), wake)

    (tmp_path / "review.md.tmp").write_text("two")
    os.replace(tmp_path / "review.md.tmp", path)
    assert _woken(wake)
    _woken(wake, 0.2)  # the directory and the old file may each report the rename

    with path.open("a") as stream:
        stream.write("three")
    assert _woken(wake)


def test_a_missing_file_is_watched_once_it_appears(hub, tmp_path):
    path = tmp_path / "later.md"
    wake = threading.Event()
    hub.watch([path], (), wake)

    path.write_text("one")
    assert _woken(wake)
    _woken(wake, 0.2)

    with path.open("a") as stream:
        stream.write("two")
    assert _woken(wake)


def test_a_new_file_in_a_watched_directory_wakes(hub, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    wake = threading.Event()
    hub.watch([inbox], (), wake)

    (inbox / "message.md").write_text("hello")

    assert _woken(wake)


def test_a_process_exit_wakes(hub):
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE
    )
    wake = threading.Event()
    hub.watch([], [child.pid], wake)
    assert not _woken(wake, 0.2)

    child.communicate()

    assert _woken(wake)


def test_an_exited_process_wakes_at_once(hub):
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    wake = threading.Event()

    hub.watch([], [child.pid], wake)

    assert _woken(wake, 0.1)


def test_loops_share_one_descriptor_and_unwatching_stops_the_wakes(hub, tmp_path):
    path = tmp_path / "shared.md"
    path.write_text("one")
    first, second = threading.Event(), threading.Event()
    unwatch_first = hub.watch([path], (), first)
    unwatch_second = hub.watch([path], (), second)
    assert len(hub._by_fd) == 2  # the file and its directory

    unwatch_first()
    path.write_text("two")

    assert _woken(second) and not first.is_set()
    unwatch_second()
    assert hub._by_fd == {}


def test_a_rewrite_of_a_file_in_a_watched_directory_wakes(hub, tmp_path):
    directory = tmp_path / "watched"
    directory.mkdir()
    existing = directory / "existing.md"
    existing.write_text("before")
    wake = threading.Event()
    hub.watch([], (), wake, contents=[directory])

    existing.write_text("after")
    assert _woken(wake)

    (directory / "later.md").write_text("one")
    assert _woken(wake)
    _woken(wake, 0.2)
    (directory / "later.md").write_text("two")
    assert _woken(wake)


def test_a_file_in_a_watched_directory_is_watched_again_after_a_rename_over_it(hub, tmp_path):
    directory = tmp_path / "watched"
    directory.mkdir()
    existing = directory / "existing.md"
    existing.write_text("one")
    wake = threading.Event()
    hub.watch([], (), wake, contents=[directory])

    (tmp_path / "replacement.md").write_text("two")
    os.replace(tmp_path / "replacement.md", existing)
    assert _woken(wake)
    _woken(wake, 0.2)

    with existing.open("a") as stream:
        stream.write("three")
    assert _woken(wake)


def test_another_file_changing_beside_a_watched_one_does_not_wake(hub, tmp_path):
    watched = tmp_path / "mine.md"
    watched.write_text("one")
    sibling = tmp_path / "theirs.md"
    sibling.write_text("one")
    wake = threading.Event()
    hub.watch([watched], (), wake)

    sibling.write_text("two")
    (tmp_path / "new.md").write_text("new")
    (tmp_path / "staged.tmp").write_text("two")
    os.replace(tmp_path / "staged.tmp", sibling)

    assert not _woken(wake, 0.3)
