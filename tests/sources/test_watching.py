"""lemonaid following a watch source through the protocol, with the plugin in fake_source.py."""

import datetime
import queue
import sys
import threading
import time

import pytest

from lemonaid.brief import attached, identity, store, waiters
from lemonaid.inbox import db
from lemonaid.plugins import command, processes, running
from lemonaid.sources import host, plugin, problems
from lemonaid.watch import delivery, notes, scouts, source_events, subscriptions, waits

from ..wait import shared as wait_shared
from .shared import CONFIG, FAKE, wait_ready


def _poller(tmp_path, delivered: list, *args: str, lemon_id="", deliver=None):
    directory = tmp_path / "cursors" / (lemon_id or "lemon.Ann") / "fake"
    directory.mkdir(parents=True, exist_ok=True)
    deliver = deliver or delivered.append
    given = args or ("item:news",)
    return source_events.Poller(
        FAKE,
        given,
        host.check(FAKE, given),
        False,
        directory,
        lemon_id,
        deliver,
        lambda problem: problems.tell_once(directory.parent, "fake", problem, deliver),
        lambda: problems.heard_again(directory.parent, "fake"),
    )


def test_check_names_the_target_or_refuses_with_the_plugins_usage():
    assert host.check(FAKE, ("item:news",)) == ("news",)
    with pytest.raises(running.Refused, match="not an item: nope"):
        host.check(FAKE, ("nope",))


def test_a_ready_notice_brings_the_next_poll_and_the_cursor_holds_what_was_delivered(
    tmp_path, fake_source_dir
):
    (fake_source_dir / "news").write_text("one\n")
    delivered: list = []
    poll = _poller(tmp_path, delivered)

    poll()
    (fake_source_dir / "news").write_text("one\ntwo\n")
    poll()  # not due: the plugin said every 600 seconds
    assert delivered == ["one"]

    (fake_source_dir / "ready").touch()
    wait_ready(poll.key)
    poll()

    assert delivered == ["one", "two"]
    assert delivery.label_of(delivered[1]) == "1 new"
    assert poll.path.read_text() == '{"seen": 2}'


def test_an_undelivered_wake_is_delivered_by_the_next_poller(tmp_path, fake_source_dir):
    (fake_source_dir / "news").write_text("one\n")

    def fail(message: str) -> None:
        raise delivery.Failed("Batch was not delivered")

    with pytest.raises(delivery.Failed):
        _poller(tmp_path, [], deliver=fail)()

    delivered: list = []
    _poller(tmp_path, delivered)()
    assert delivered == ["one"]


def test_a_problem_reaches_the_lemon_once_until_a_poll_succeeds(tmp_path, fake_source_dir):
    (fake_source_dir / "problem").write_text("sign in, please")
    delivered: list = []
    poll = _poller(tmp_path, delivered)

    poll()
    poll.next_at = 0
    poll()
    assert delivered == ["sign in, please"]

    (fake_source_dir / "problem").unlink()
    poll.next_at = 0
    poll()
    (fake_source_dir / "problem").write_text("sign in again")
    poll.next_at = 0
    poll()
    assert delivered == ["sign in, please", "sign in again"]


def test_an_end_is_told_once_leaves_watching_and_the_plugin_forgets_it(tmp_path, fake_source_dir):
    path = store.create("following", datetime.date(2026, 11, 26))
    with db.connect() as conn:
        attached.attach(conn, "claude:follower", path)
        lemon_id = identity.ensure(conn, path)
    path.write_text(waiters.add(path.read_text(), "lemonaid watch fake item:news --end"))
    delivered: list = []
    poll = _poller(tmp_path, delivered, "item:news", "--end", lemon_id=lemon_id)

    poll()
    poll.next_at = 0
    poll()

    assert delivered == ["Stopped following news: it ended; its line left ## Watching"]
    assert waiters.commands(path.read_text()) == []
    assert not poll.path.exists()
    assert (fake_source_dir / "forgotten").read_text() == f"{poll.key}\n"


def test_a_plugin_that_will_not_start_is_tried_again_later(tmp_path):
    broken = plugin.Source(command.Plugin("broken", (sys.executable, "-c", "pass")))
    directory = tmp_path / "cursors" / "lemon.Ann" / "broken"
    directory.mkdir(parents=True)
    poll = source_events.Poller(broken, ("x",), ("x",), False, directory, "", print, print)

    poll()

    assert poll.next_at > 0 and not poll.ended


def test_a_brief_line_naming_a_configured_source_is_a_subscription(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text(CONFIG)
    monkeypatch.setenv("LEMONAID_CONFIG", str(tmp_path / "config.toml"))
    text = (
        wait_shared.BRIEF
        + "- `lemonaid watch fake item:news --me Ann`\n- `lemonaid watch fake bad`\n"
    )

    reading = subscriptions.report(text, tmp_path)

    [spec] = [s for s in reading.specs if s.kind == "fake"]
    assert (spec.target, spec.args, spec.me) == (("news",), ("item:news",), "Ann")
    assert any("not an item: bad" in problem for problem in reading.problems)


def test_a_wake_without_a_cursor_is_delivered_and_the_cursor_kept(tmp_path, monkeypatch):
    delivered: list = []
    poll = _poller(tmp_path, delivered)
    poll.path.write_text('{"seen": 0}')
    monkeypatch.setattr(processes, "ask", lambda *args: "wake\ntext event\nevery 10\n")

    poll()

    assert delivered == ["event"]
    assert poll.path.read_text() == '{"seen": 0}'


@pytest.mark.parametrize("early", [False, True])
def test_a_plugin_that_dies_is_started_again_and_polled_for_every_subscription(
    tmp_path, fake_source_dir, monkeypatch, early
):
    monkeypatch.setattr(processes, "RETRY_AFTER", 0.5)
    delivered: dict[str, list] = {"news": [], "sport": []}
    polls = {
        name: _poller(tmp_path, delivered[name], f"item:{name}", lemon_id=f"lemon.{name}")
        for name in delivered
    }
    wakes = {name: threading.Event() for name in delivered}
    for name, poll in polls.items():
        poll.wake_with(wakes[name])
        poll()
    started = processes._running[host.launch(FAKE)]
    started._proc.kill()  # between requests: its notice reader finds it gone
    deadline = time.monotonic() + 5
    while processes._running.get(host.launch(FAKE)) is started:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    if early:
        for poll in polls.values():
            poll()  # a regular tick during the backoff is refused
    for wake in wakes.values():
        wake.clear()

    assert all(wake.wait(5) for wake in wakes.values())  # once it may be started again
    for name in delivered:
        (fake_source_dir / name).write_text(f"{name} after the crash\n")
    time.sleep(0.05)
    for poll in polls.values():
        poll()

    assert delivered == {"news": ["news after the crash"], "sport": ["sport after the crash"]}


def test_a_plugin_that_will_not_start_is_not_started_again_at_once(monkeypatch):
    starts: list = []

    def refuse(*args, **kwargs):
        starts.append(args)
        raise running.Failed("no such program")

    monkeypatch.setattr(running, "Running", refuse)
    for _ in range(2):
        with pytest.raises(running.Failed):
            processes.ask(host.launch(FAKE), "check", [], "")

    assert len(starts) == 1


def test_a_ready_notice_wakes_an_idle_scout_at_once(tmp_path, fake_source_dir, monkeypatch):
    (tmp_path / "config.toml").write_text(CONFIG)
    monkeypatch.setenv("LEMONAID_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setattr(scouts, "_SETTLE", 0.0)

    class _Idle(type(waits.TIMERS)):
        idle = 60.0

    spec = subscriptions.Subscription("fake", ("news",), interval=1, quiet=0, args=("item:news",))
    output: queue.Queue = queue.Queue()
    root = tmp_path / "cursors" / "lemon.Ann"
    scout = scouts.Scout(spec, root, "", output, (), notes.none, pacing=_Idle())
    scout.thread.start()
    try:
        assert scout.ready.wait(5)
        time.sleep(1.5)  # past its busy start, into the idle sleep
        (fake_source_dir / "news").write_text("news\n")
        (fake_source_dir / "ready").touch()

        pending = output.get(timeout=5)
        pending.delivered = True
        pending.acknowledged.set()
        assert pending.message == "news"
    finally:
        scout.stop()
        scout.thread.join(5)
