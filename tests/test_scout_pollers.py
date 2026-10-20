import os
import threading
import time

from lemonaid.watch import (
    github_api,
    github_failures,
    pr_activity,
    scout_pollers,
    subscriptions,
)


def test_a_settled_doc_reports_current_unanswered_threads_without_an_extra_delay(tmp_path):
    doc = tmp_path / "review.md"
    doc.write_text('{{authorId="human" author="Human">>question<<}}')
    os.utime(doc, (time.time() - 60, time.time() - 60))
    spec = subscriptions.Subscription("doc", (str(doc),), "Author (IndexElf)", quiet=20)
    sent = []

    def deliver(message):
        sent.append(message)
        return True

    poll = scout_pollers.open_poller(spec, tmp_path / "cursors", "", deliver, ())
    poll()
    assert len(sent) == 1 and "question" in sent[0]


def test_an_already_closed_pr_is_silent_and_stops_being_polled(tmp_path, monkeypatch):
    snapshot = pr_activity.Snapshot("a" * 40, "MERGED", False, "", [], "main", "MERGEABLE", [])
    fetched, sent = [], []

    def fetch(*args, **kwargs):
        fetched.append(args)
        return snapshot

    monkeypatch.setattr(pr_activity, "fetch", fetch)
    spec = subscriptions.Subscription("pr", ("owner/repo", "12"), comments=True, ci=True)
    poll = scout_pollers.open_poller(spec, tmp_path / "cursors", "", sent.append, ())
    poll()
    poll()
    assert len(fetched) == 1
    assert sent == []


def test_github_failure_is_reported_once_across_rearms_and_again_after_recovery(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(github_failures, "_retry_delay", lambda attempts, interval: 0)
    snapshot = pr_activity.Snapshot("b" * 40, "OPEN", False, "", [], "main", "MERGEABLE", [])
    state = [None]
    monkeypatch.setattr(pr_activity, "fetch", lambda *args, **kwargs: state[0])
    spec = subscriptions.Subscription("pr", ("o/r", "12"), comments=True, ci=True)
    sent = []
    for _ in range(2):
        poll = scout_pollers.open_poller(spec, tmp_path, "", sent.append, ())
        for _ in range(3):
            poll()
    assert len(sent) == 1
    state[0] = snapshot
    poll()
    state[0] = None
    for _ in range(3):
        poll()
    assert len(sent) == 2


def test_a_body_event_names_the_quiet_period_enforced_by_its_scout(tmp_path):
    doc = tmp_path / "review.md"
    doc.write_text("Before\n")
    spec = subscriptions.Subscription("doc", (str(doc),), edits=True, quiet=20)
    root = tmp_path / "cursors"
    scout_pollers.open_poller(spec, root, "", lambda message: True, ())
    doc.write_text("After\n")
    os.utime(doc, (time.time() - 60, time.time() - 60))
    sent = []
    poll = scout_pollers.open_poller(
        spec, root, "", lambda message: sent.append(message) or True, ()
    )
    poll()
    assert len(sent) == 1 and "quiet for 20s" in sent[0]


def test_a_comment_is_reported_at_the_settle_and_the_body_edit_after_the_quiet_period(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(scout_pollers, "_THREAD_SETTLE", 0.05)
    doc = tmp_path / "review.md"
    doc.write_text("Body\n")
    os.utime(doc, (time.time() - 60, time.time() - 60))
    spec = subscriptions.Subscription(
        "doc", (str(doc),), "Author (IndexElf)", edits=True, quiet=0.3
    )
    sent = []
    poll = scout_pollers.open_poller(
        spec, tmp_path / "cursors", "", lambda message: sent.append(message) or True, ()
    )
    poll()
    doc.write_text('Body\n{{authorId="human" author="Human">>question<<}}\nmore body\n')
    poll()
    assert sent == []  # the file just changed

    time.sleep(0.1)
    poll()
    assert len(sent) == 1 and "question" in sent[0] and "body of" not in sent[0]

    time.sleep(0.3)
    poll()
    poll()
    assert len(sent) == 2 and "body of" in sent[1]


def test_a_failed_read_waits_longer_each_time_before_the_next(tmp_path, monkeypatch):
    fetched = []
    monkeypatch.setattr(pr_activity, "fetch", lambda *args, **kwargs: fetched.append(1))
    delays = []

    def delay(attempts, interval):
        delays.append(attempts)
        return 0 if attempts < 2 else 3600

    monkeypatch.setattr(github_failures, "_retry_delay", delay)
    spec = subscriptions.Subscription("pr", ("o/r", "12"))
    poll = scout_pollers.open_poller(spec, tmp_path, "", lambda message: True, ())
    for _ in range(4):
        poll()
    assert len(fetched) == 2
    assert delays == [1, 2]


def test_a_quota_pause_is_told_once_per_lemon_and_never_as_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr(github_api, "_JITTER", 0)
    monkeypatch.setattr(github_failures, "_retry_delay", lambda attempts, interval: 0)
    github_api._pause(github_api.Pause(time.time() + 3600, "quota"))
    monkeypatch.setattr(pr_activity, "fetch", lambda *args, **kwargs: None)
    sent = []
    for number in ("12", "13"):
        spec = subscriptions.Subscription("pr", ("o/r", number))
        poll = scout_pollers.open_poller(spec, tmp_path, "", sent.append, ())
        for _ in range(3):
            poll()
    assert len(sent) == 1
    assert "quota is used up until" in sent[0]


def test_concurrent_scouts_tell_a_lemon_about_one_pause_once(tmp_path, monkeypatch):
    monkeypatch.setattr(github_api, "_JITTER", 0)
    github_api._pause(github_api.Pause(time.time() + 3600, "quota"))
    sent, second = [], threading.Event()

    def deliver(message):
        sent.append(message)
        second.wait(0.5)  # a second scout may try to deliver while this one waits
        return True

    def scout(number):
        failure = tmp_path / "failures" / f"{number}.json"
        if number == "13":
            second.set()
        github_failures.failed(tmp_path, failure, f"o/r#{number}", deliver, 60)

    threads = [threading.Thread(target=scout, args=(n,)) for n in ("12", "13")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert len(sent) == 1


def test_a_read_that_succeeds_during_a_pause_keeps_the_pause_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(github_api, "_JITTER", 0)
    github_api._pause(github_api.Pause(time.time() + 3600, "quota"))
    sent = []
    github_failures.failed(tmp_path, tmp_path / "failures" / "12.json", "o/r#12", sent.append, 60)
    github_failures.recovered(tmp_path, tmp_path / "failures" / "13.json")
    github_failures.failed(tmp_path, tmp_path / "failures" / "14.json", "o/r#14", sent.append, 60)
    assert len(sent) == 1
