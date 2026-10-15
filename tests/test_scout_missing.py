import os

from lemonaid.watch import path_presence, scout_pollers, subscriptions


def test_the_doc_scout_delivers_disappearance_and_does_not_follow(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(path_presence.time, "monotonic", lambda: clock[0])
    doc = tmp_path / "note.md"
    doc.write_text("body")
    spec = subscriptions.Subscription("doc", (str(doc),), quiet=2)
    sent = []
    poll = scout_pollers.open_poller(
        spec, tmp_path / "cursors", "", lambda msg: sent.append(msg) or True, ()
    )
    renamed = tmp_path / "new.md"
    doc.rename(renamed)
    poll()
    assert sent == []
    clock[0] = 3
    poll()
    assert len(sent) == 1 and str(renamed) in sent[0]
    renamed.write_text('{{author="Human">>new question<<}}')
    poll()
    assert len(sent) == 1
    assert spec.target == (str(doc),)


def test_scout_save_gaps_reset_the_missing_quiet_period(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(path_presence.time, "monotonic", lambda: clock[0])
    doc = tmp_path / "note.md"
    doc.write_text("body")
    spec = subscriptions.Subscription("doc", (str(doc),), quiet=2)
    sent = []
    poll = scout_pollers.open_poller(
        spec, tmp_path / "cursors", "", lambda msg: sent.append(msg) or True, ()
    )
    doc.rename(tmp_path / "backup")
    poll()
    clock[0] = 1
    doc.write_text("replacement still settling")
    poll()
    clock[0] = 2
    doc.rename(tmp_path / "renamed")
    poll()
    assert sent == []
    clock[0] = 4
    poll()
    assert len(sent) == 1 and str(tmp_path / "renamed") in sent[0]
    assert str(tmp_path / "backup") not in sent[0]


def test_scout_reappearance_after_rearm_allows_another_missing_notice(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(path_presence.time, "monotonic", lambda: clock[0])
    doc = tmp_path / "note.md"
    doc.write_text("body")
    spec = subscriptions.Subscription("doc", (str(doc),), quiet=2)
    sent = []
    root = tmp_path / "cursors"

    def deliver(msg):
        return sent.append(msg) or True

    poll = scout_pollers.open_poller(spec, root, "", deliver, ())
    doc.unlink()
    poll()
    clock[0] = 3
    poll()
    assert len(sent) == 1
    poll = scout_pollers.open_poller(spec, root, "", deliver, ())
    doc.write_text("new body still settling")
    poll()
    doc.unlink()
    poll()
    clock[0] = 6
    poll()
    assert len(sent) == 2


def test_scout_observed_atomic_save_refreshes_identity_before_settling(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(path_presence.time, "monotonic", lambda: clock[0])
    doc = tmp_path / "note.md"
    doc.write_text("body")
    spec = subscriptions.Subscription("doc", (str(doc),), quiet=2)
    sent = []
    poll = scout_pollers.open_poller(
        spec, tmp_path / "cursors", "", lambda msg: sent.append(msg) or True, ()
    )
    temp = tmp_path / "save"
    temp.write_text("changed body still settling")
    os.replace(temp, doc)
    poll()
    renamed = tmp_path / "new.md"
    doc.rename(renamed)
    poll()
    clock[0] = 3
    poll()
    assert len(sent) == 1 and str(renamed) in sent[0]
