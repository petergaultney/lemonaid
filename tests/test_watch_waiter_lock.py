import fcntl
import threading

from lemonaid.watch import waiter_lock


def test_a_status_probe_neither_blocks_a_starting_waiter_nor_rewrites_the_holder(tmp_path):
    lock_path = tmp_path / "doc.lock"
    lock_path.write_text("pid 1 since then: an earlier waiter\n")
    probe = lock_path.open()
    fcntl.flock(probe, fcntl.LOCK_SH | fcntl.LOCK_NB)  # a status probe caught mid-flight
    threading.Timer(0.2, probe.close).start()

    assert waiter_lock.held(lock_path) is False
    assert lock_path.read_text() == "pid 1 since then: an earlier waiter\n"
    held = waiter_lock.acquire(lock_path)

    assert held is not None
    assert waiter_lock.held(lock_path) is True
    assert waiter_lock.acquire(lock_path, grace=0.1) is None
    held.close()


def test_no_lock_file_means_no_waiter(tmp_path):
    assert waiter_lock.held(tmp_path / "missing.lock") is False
