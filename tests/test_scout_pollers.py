import os
import time

from lemonaid.watch import pr_activity, scout_pollers, subscriptions


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
