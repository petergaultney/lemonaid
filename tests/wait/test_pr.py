import time

from lemonaid.messages import store
from lemonaid.watch import github_api, pr_activity

from . import shared


def test_a_saved_pr_head_wins_over_the_same_stale_subscription_on_rearm(tmp_path, monkeypatch):
    snapshot = pr_activity.Snapshot("b" * 40, "OPEN", False, "", [], "main", "MERGEABLE", [])
    monkeypatch.setattr(pr_activity, "fetch", lambda *args, **kwargs: snapshot)
    text = (
        shared.BRIEF
        + f"- `lemonaid watch pr --wait 12 --repo o/r --head {'a' * 40} --interval .01`\n"
    )
    first = []
    _path, _inbox, _root, stop, thread, errors = shared.start(tmp_path, text, first.append)
    try:
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert "head moved" in first[0]
    finally:
        stop.set()
        thread.join(5)
    later = []
    _path, inbox, _root, stop, thread, errors = shared.start(tmp_path, text, later.append)
    try:
        time.sleep(0.15)
        assert thread.is_alive() and later == []
        store.send(inbox, "wake once", "other.IndexElf")
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(later) == 1 and "head moved" not in later[0]
    finally:
        stop.set()
        thread.join(5)


def test_already_passed_ci_is_a_first_wait_baseline(tmp_path, monkeypatch):
    snapshot = pr_activity.Snapshot(
        "b" * 40,
        "OPEN",
        False,
        "",
        [],
        "main",
        "MERGEABLE",
        [pr_activity.Check("test", False, "passed")],
    )
    monkeypatch.setattr(pr_activity, "fetch", lambda *args, **kwargs: snapshot)
    text = shared.BRIEF + "- `lemonaid watch pr --wait 12 --repo o/r --ci --interval .01`\n"
    sent = []
    _path, inbox, root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        shared.eventually(lambda: bool(list((root / "pr").glob("*.merge.json"))))
        time.sleep(0.15)
        assert thread.is_alive() and sent == []
        store.send(inbox, "first wake", "other.IndexElf")
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and "CI passed" not in sent[0]
    finally:
        stop.set()
        thread.join(5)


def test_two_paused_pr_scouts_deliver_one_quota_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(github_api, "_JITTER", 0)
    github_api._pause(github_api.Pause(time.time() + 3600, "quota"))
    monkeypatch.setattr(pr_activity, "fetch", lambda *args, **kwargs: None)
    text = (
        shared.BRIEF
        + "- `lemonaid watch pr --wait 12 --repo o/r --interval .01`\n"
        + "- `lemonaid watch pr --wait 13 --repo o/r --interval .01`\n"
    )
    sent = []
    _path, _inbox, _root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and sent[0].count("quota is used up until") == 1
    finally:
        stop.set()
        thread.join(5)
