"""A detector that finds a change on its fallback poll keeps polling until the change settles."""

import queue
import threading
import time

from lemonaid.watch import notes, scouts, subscriptions


class _NoEvents:
    """Pacing whose events never arrive, as when one is missed."""

    idle = 0.8

    def watch(self, paths, pids, wake: threading.Event, contents=()):
        return lambda: None

    def wake_all(self) -> None:
        pass


def test_a_change_found_without_an_event_is_delivered_after_its_quiet_period(tmp_path, monkeypatch):
    watched = tmp_path / "watched.md"
    watched.write_text("before")
    monkeypatch.setattr(scouts, "_SETTLE", 0.02)
    output: queue.Queue[scouts.Pending] = queue.Queue()
    spec = subscriptions.Subscription("file", (str(watched),), interval=0.01, quiet=0.1)
    scout = scouts.Scout(spec, tmp_path / "cursors", "", output, (), notes.none, _NoEvents())
    scout.thread.start()
    try:
        assert scout.ready.wait(1)
        time.sleep(0.3)  # past the startup window, so the scout sleeps its idle interval
        start = time.monotonic()
        watched.write_text("after")

        pending = output.get(timeout=3)

        assert time.monotonic() - start < _NoEvents.idle + spec.quiet + 0.3
        pending.delivered = True
        pending.acknowledged.set()
    finally:
        scout.stop()
        scout.thread.join(2)
