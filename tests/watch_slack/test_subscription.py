"""A `lemonaid watch slack` line in a brief, read as a subscription and run by the watcher."""

import threading
import time

import pytest

from lemonaid.slack import api, session, wakes
from lemonaid.watch import brief_record, delivery, kqueue_waits, scouts, subscriptions

from ..slack.shared import LINK, SESSION, THREAD, Slack, reply
from ..wait import shared

REPLY_LINK = f"https://acme.slack.com/archives/C0TEAM/p1794857990000002?thread_ts={THREAD.ts}"


def _slack_specs(text: str, tmp_path) -> list[subscriptions.Subscription]:
    return [s for s in subscriptions.read(text, tmp_path) if s.kind == "slack"]


def test_a_line_naming_any_link_into_a_thread_follows_that_thread(tmp_path):
    text = shared.BRIEF + f"- `lemonaid watch slack {REPLY_LINK} --after 1794857980.000001`\n"

    [spec] = _slack_specs(text, tmp_path)

    assert spec.target == (THREAD.channel, THREAD.ts)
    assert (spec.link, spec.after, spec.brief_done) == (LINK, "1794857980.000001", False)
    assert brief_record._identity(f"lemonaid watch slack {LINK}") == brief_record._identity(
        f"lemonaid watch slack '{REPLY_LINK}'"
    )


def test_a_channel_line_follows_the_channel_with_its_pattern(tmp_path):
    channel = "https://acme.slack.com/archives/C0TEAM"
    text = shared.BRIEF + f"- `lemonaid watch slack {channel} --match '(?i)deploy|release'`\n"

    [spec] = _slack_specs(text, tmp_path)

    assert (spec.target, spec.link, spec.match) == (("C0TEAM",), channel, "(?i)deploy|release")
    assert brief_record._identity(f"lemonaid watch slack {channel}") != brief_record._identity(
        f"lemonaid watch slack {LINK}"
    )


def test_a_done_brief_marks_its_slack_subscriptions_to_end(tmp_path):
    text = shared.BRIEF.replace("Brief-ID:", "Status: done\n\nBrief-ID:")

    [spec] = _slack_specs(text + f"- `lemonaid watch slack {LINK}`\n", tmp_path)

    assert spec.brief_done


def test_a_signalled_reply_reaches_the_lemon_in_its_next_batch(tmp_path, monkeypatch):
    slack = Slack(replies=[reply("1794857980.000001", "an old reply")])
    monkeypatch.setattr(api, "call", slack)
    monkeypatch.setattr(session, "load", lambda: SESSION)
    sent: list[str] = []
    text = shared.BRIEF + f"- `lemonaid watch slack {LINK}`\n"
    _path, _inbox, root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        shared.eventually(lambda: (root / "slack" / f"{THREAD.channel}-{THREAD.ts}.json").exists())
        slack.replies.append(reply("1794857990.000002", "a new reply"))
        time.sleep(0.01)
        wakes.signal(THREAD.channel, THREAD.ts)
        thread.join(5)
        assert not thread.is_alive() and not errors
        [batch] = sent
        assert batch.startswith(f"[slack: {THREAD.channel}, {THREAD.ts}] Slack thread {LINK}")
        assert "a new reply" in batch and "an old reply" not in batch
    finally:
        stop.set()
        thread.join(5)


@pytest.mark.skipif(not kqueue_waits.available(), reason="the scout host sleeps on kqueue")
def test_the_gateways_signal_wakes_a_sleeping_scout_at_once():
    spec = subscriptions.Subscription("slack", (THREAD.channel, THREAD.ts), link=LINK)
    sources = scouts._sources(spec)  # before any poll has made the thread's directory
    wake = threading.Event()
    unwatch = kqueue_waits.Hub().watch(sources.paths, sources.pids, wake, sources.contents)
    try:
        time.sleep(0.05)
        wakes.signal(THREAD.channel, THREAD.ts)
        assert wake.wait(2)
    finally:
        unwatch()


def test_a_lemon_following_two_threads_hears_once_about_signing_in_after_a_failed_batch(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(session, "load", lambda: None)
    other = "https://acme.slack.com/archives/C0OTHER/p1794850000000001"
    text = shared.BRIEF + f"- `lemonaid watch slack {LINK}`\n- `lemonaid watch slack {other}`\n"

    def fail(message: str) -> None:
        raise delivery.Failed("Batch was not delivered")

    _path, _inbox, _root, stop, thread, errors = shared.start(tmp_path, text, fail)
    thread.join(5)
    stop.set()
    assert not thread.is_alive() and errors

    sent: list[str] = []
    _path, _inbox, _root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        thread.join(5)
        assert not thread.is_alive() and not errors
        [batch] = sent
        assert batch.count("lemonaid slack signin") == 1
    finally:
        stop.set()
        thread.join(5)
