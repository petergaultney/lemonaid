import os

from lemonaid.grove.layout import state
from lemonaid.messages import store
from lemonaid.watch import cursors, subscription_state, wait_state, waiter_lock


def _stamp(path):
    stat = path.stat()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def test_unchanged_subscriptions_do_not_replace_cursors(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("# Idle lemon\n")
    root = tmp_path / "cursors"
    first = subscription_state.read(brief, root, tmp_path)
    stamps = {path: _stamp(path) for path in root.iterdir()}

    for _ in range(10):
        assert subscription_state.read(brief, root, tmp_path) == first
    assert {path: _stamp(path) for path in root.iterdir()} == stamps

    cursor = root / "brief-problems.json"
    cursors.write_json(cursor, ["changed"])
    assert cursor.read_text() == '["changed"]'
    cursor.unlink()
    cursors.write_json(cursor, [])
    assert cursor.read_text() == "[]"
    assert not list(root.glob(".*"))


def test_receiving_without_messages_keeps_the_lock_unchanged(tmp_path):
    lock = tmp_path / ".receive.lock"
    lock.write_text("existing lock")
    before = _stamp(lock)
    for _ in range(10):
        with store.receive_lock(tmp_path, wait=False) as held:
            assert held
    assert _stamp(lock) == before
    assert lock.read_text() == "existing lock"


def test_noop_grove_updates_keep_both_files_unchanged(tmp_path):
    target = tmp_path / "grove.json"
    state.update(lambda saved: {**saved, "trees": {"one": {}}}, target)
    before = {path: _stamp(path) for path in tmp_path.iterdir()}
    for _ in range(10):
        state.update(lambda saved: saved, target)
    assert {path: _stamp(path) for path in tmp_path.iterdir()} == before


def test_heartbeat_writes_are_bounded_and_stalled_waiters_still_go_deaf(tmp_path, monkeypatch):
    lemon = "idle.IndexElf"
    lock = wait_state.lock_path(lemon)
    lock.parent.mkdir(parents=True)
    now = wait_state.time.time()
    monkeypatch.setattr(wait_state.time, "time", lambda: now)
    beat = lock.with_suffix(".beat")
    with waiter_lock.acquire(lock):
        wait_state.beat(lemon)
        before = _stamp(beat)
        for _ in range(19):
            now += 0.5
            wait_state.beat(lemon)
            assert wait_state.is_armed(lemon)
        assert _stamp(beat) == before

        os.utime(beat, (now - 11, now - 11))
        wait_state.beat(lemon)
        assert _stamp(beat) != before
        now += wait_state.STALE + 1
        assert wait_state.deaf(lemon)
        assert not wait_state.is_armed(lemon)

        # A future timestamp must not suppress heartbeats after a clock correction.
        os.utime(beat, (now + 60, now + 60))
        wait_state.beat(lemon)
        assert beat.stat().st_mtime < now
