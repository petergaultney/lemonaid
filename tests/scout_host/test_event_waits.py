"""An idle loop on kqueue events delivers as soon as a source changes, not at its idle sleep."""

import threading
import time

import pytest

from lemonaid.messages import store
from lemonaid.watch import batch_wait, kqueue_waits, scouts

pytestmark = pytest.mark.skipif(not kqueue_waits.available(), reason="kqueue is macOS and BSD only")

_BRIEF = "# task\n\nBrief-ID: task.IndexElf\n\n## Watching\n"


@pytest.fixture
def hub(monkeypatch) -> kqueue_waits.Hub:
    hub = kqueue_waits.Hub()
    monkeypatch.setattr(hub, "idle", 30.0)
    monkeypatch.setattr(scouts, "_SETTLE", 0.2)
    return hub


def _waiting(tmp_path, hub, text: str) -> tuple[threading.Thread, list[str]]:
    path = tmp_path / "brief.md"
    path.write_text(text)
    inbox = store.inbox_for_id("task.IndexElf")
    inbox.mkdir(parents=True, exist_ok=True)
    sent: list[str] = []
    thread = threading.Thread(
        target=lambda: batch_wait.wait(
            path,
            inbox,
            tmp_path / "cursors",
            "",
            sent.append,
            lambda: True,
            cwd=tmp_path,
            interval=0.01,
            quiet=0.05,
            pacing=hub,
        ),
        daemon=True,
    )
    thread.start()
    time.sleep(1)  # past the detectors' settle window, so the loop sleeps on events
    return thread, sent


def test_a_message_reaches_an_idle_loop_at_once(tmp_path, hub):
    thread, sent = _waiting(tmp_path, hub, _BRIEF)

    store.send(store.inbox_for_id("task.IndexElf"), "hello", "other.IndexElf")

    thread.join(5)
    assert not thread.is_alive() and "hello" in sent[0]


def test_a_watched_file_change_reaches_an_idle_loop_at_once(tmp_path, hub):
    target = tmp_path / "watched.txt"
    target.write_text("before")
    thread, sent = _waiting(
        tmp_path,
        hub,
        _BRIEF + f"- `lemonaid watch file --wait {target} --interval .01 --quiet 0`\n",
    )

    target.write_text("after")

    thread.join(5)
    assert not thread.is_alive() and str(target) in sent[0]
