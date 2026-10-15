"""Missing documents and folders produce advice without changing watch targets."""

import os

import pytest

from lemonaid.watch import doc_events, file_events, path_presence


def test_a_renamed_doc_is_suggested_once_across_rearms(tmp_path):
    doc = tmp_path / "old.md"
    doc.write_text("body")
    root = tmp_path / "cursors"
    watch = doc_events.open_watch(root, doc, "me", [], False, 0)
    renamed = tmp_path / "new.md"
    doc.rename(renamed)
    sent = []
    assert (
        doc_events.poll(watch, lambda msg: sent.append(msg) or True) is doc_events.Outcome.DELIVERED
    )
    assert str(doc) in sent[0] and str(renamed) in sent[0]
    assert "possible replacement" in sent[0] and "Confirm" in sent[0]
    assert watch.doc == doc
    assert doc_events.poll(watch, lambda _: True) is doc_events.Outcome.NOTHING
    rearmed = doc_events.open_watch(root, doc, "me", [], False, 0)
    assert doc_events.poll(rearmed, lambda _: True) is doc_events.Outcome.NOTHING


def test_a_move_while_unarmed_is_suggested(tmp_path):
    doc = tmp_path / "old.md"
    doc.write_text("body")
    root = tmp_path / "cursors"
    doc_events.open_watch(root, doc, "me", [], False, 0)
    destination = tmp_path / "nearby"
    destination.mkdir()
    renamed = destination / "new.md"
    doc.rename(renamed)
    sent = []
    watch = doc_events.open_watch(root, doc, "me", [], False, 0)
    doc_events.poll(watch, lambda msg: sent.append(msg) or True)
    assert str(renamed) in sent[0]


def test_a_deleted_doc_is_reported_without_a_destination(tmp_path):
    doc = tmp_path / "old.md"
    doc.write_text("body")
    watch = doc_events.open_watch(tmp_path / "cursors", doc, "me", [], False, 0)
    # Keep the original object allocated so this test cannot manufacture inode reuse.
    with doc.open():
        doc.unlink()
        (tmp_path / "unrelated.md").write_text("body")
        sent = []
        doc_events.poll(watch, lambda msg: sent.append(msg) or True)
    assert "no longer present" in sent[0] and "deleted or moved" in sent[0]
    assert "possible replacement" not in sent[0]


def test_a_failed_notice_is_retried_after_rearm(tmp_path):
    doc = tmp_path / "old.md"
    doc.write_text("body")
    root = tmp_path / "cursors"
    watch = doc_events.open_watch(root, doc, "me", [], False, 0)
    doc.rename(tmp_path / "new.md")
    assert doc_events.poll(watch, lambda _: False) is doc_events.Outcome.FAILED
    watch = doc_events.open_watch(root, doc, "me", [], False, 0)
    assert doc_events.poll(watch, lambda _: True) is doc_events.Outcome.DELIVERED


def test_a_save_gap_does_not_report_and_reappearance_resets_missing_notice(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(path_presence.time, "monotonic", lambda: clock[0])
    doc = tmp_path / "note.md"
    doc.write_text("body")
    watch = doc_events.open_watch(tmp_path / "cursors", doc, "me", [], False, 2)
    backup = tmp_path / "note.md~"
    doc.rename(backup)
    assert doc_events.poll(watch, lambda _: True) is doc_events.Outcome.NOTHING
    doc.write_text("replacement")
    clock[0] = 3
    assert doc_events.poll(watch, lambda _: True) is doc_events.Outcome.NOTHING
    doc.unlink()
    assert doc_events.poll(watch, lambda _: True) is doc_events.Outcome.NOTHING
    clock[0] = 6
    assert doc_events.poll(watch, lambda _: True) is doc_events.Outcome.DELIVERED
    doc.write_text("back")
    doc_events.poll(watch, lambda _: True)
    doc.unlink()
    doc_events.poll(watch, lambda _: True)
    clock[0] = 9
    assert doc_events.poll(watch, lambda _: True) is doc_events.Outcome.DELIVERED


@pytest.mark.parametrize("folder", [False, True])
def test_file_watch_suggests_moves_and_retains_original_target(tmp_path, folder):
    target = tmp_path / "target"
    target.mkdir() if folder else target.write_text("body")
    root = tmp_path / "cursors"
    file_events.open_watch(root, [target], "me", 0)
    renamed = tmp_path / "renamed"
    target.rename(renamed)
    watch = file_events.open_watch(root, [target], "me", 0)
    sent = []
    assert file_events.poll(watch, sent.append)
    assert str(renamed) in sent[0] and "Confirm" in sent[0]
    assert watch.paths == [target]
    watch = file_events.open_watch(root, [target], "me", 0)
    assert not file_events.poll(watch, sent.append)


def test_multiple_file_targets_keep_separate_identities_when_reordered(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.write_text("a")
    second.write_text("b")
    root = tmp_path / "cursors"
    file_events.open_watch(root, [first, second], "me", 0)
    renamed = tmp_path / "renamed"
    first.rename(renamed)
    watch = file_events.open_watch(root, [second, first], "me", 0)
    sent = []
    file_events.poll(watch, sent.append)
    assert str(renamed) in sent[0]


def test_ignore_removed_does_not_search_or_deliver(tmp_path, monkeypatch):
    target = tmp_path / "file"
    target.write_text("body")
    watch = file_events.open_watch(tmp_path / "cursors", [target], "me", 0, True)
    target.rename(tmp_path / "new")
    monkeypatch.setattr(path_presence, "missing_message", lambda *args: pytest.fail("searched"))
    assert not file_events.poll(watch, lambda _: pytest.fail("delivered"))


def test_atomic_save_refreshes_identity_for_a_later_rename(tmp_path):
    doc = tmp_path / "note.md"
    doc.write_text("same content")
    watch = doc_events.open_watch(tmp_path / "cursors", doc, "me", [], False, 0)
    temp = tmp_path / "temp"
    temp.write_text("same content")
    os.replace(temp, doc)
    assert doc_events.poll(watch, lambda _: True) is doc_events.Outcome.NOTHING
    renamed = tmp_path / "new.md"
    doc.rename(renamed)
    sent = []
    doc_events.poll(watch, lambda msg: sent.append(msg) or True)
    assert str(renamed) in sent[0]
