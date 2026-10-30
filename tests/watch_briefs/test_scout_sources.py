"""A children detector sleeping on events still sees watched lemons and children linked later.

Adapted from the #448 reviewer's probe.
"""

import queue
import time

import pytest

from lemonaid.brief import lemon_table
from lemonaid.watch import kqueue_waits, lemon_liveness, notes, scouts, subscriptions

from .shared import lemon, link

pytestmark = pytest.mark.skipif(not kqueue_waits.available(), reason="kqueue is macOS and BSD only")


@pytest.mark.parametrize("watched", ["listed", "linked later"])
def test_a_status_change_arrives_after_one_idle_sleep_at_most(tmp_path, monkeypatch, watched):
    parent, _ = lemon("parent", channel="codex:parent")
    other, path = lemon("other", channel="codex:other")
    monkeypatch.setattr(lemon_liveness, "probe", lambda *args: {})
    monkeypatch.setattr(scouts, "_SETTLE", 0.02)
    hub = kqueue_waits.Hub()
    hub.idle = 0.8
    spec = subscriptions.Subscription(
        "briefs",
        (parent,),
        interval=0.01,
        quiet=0.1,
        lemons=(lemon_table.Row(other),) if watched == "listed" else (),
    )
    output: queue.Queue[scouts.Pending] = queue.Queue()
    scout = scouts.Scout(spec, tmp_path / "cursors", "", output, (), notes.none, hub)
    scout.thread.start()
    try:
        assert scout.ready.wait(1)
        time.sleep(0.3)  # past the startup window, so the scout sleeps on events
        start = time.monotonic()
        path.write_text(path.read_text().replace("Status: working", "Status: done"))
        if watched == "linked later":
            link(other, parent)

        pending = output.get(timeout=3)

        assert time.monotonic() - start < hub.idle + spec.quiet + 0.15
        pending.delivered = True
        pending.acknowledged.set()
    finally:
        scout.stop()
        scout.thread.join(2)
