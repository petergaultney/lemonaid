"""A save to the old home after cutover stops brief and message commands until reconciled."""

import pytest

from lemonaid.brief import attached, store
from lemonaid.home import guard, journal, layout, migrate, reconcile
from lemonaid.inbox import db
from lemonaid.messages import store as message_store

from .shared import old_home_with_work


def _late_save_before_cutover(monkeypatch, name: str, text: str) -> None:
    write_atomic = journal.write_atomic

    def save_then_cut_over(path, content):
        if path.name == layout.CUTOVER:
            layout.legacy_dir().mkdir(exist_ok=True)
            (layout.legacy_dir() / name).write_text(text)  # an editor's save, just too late
        write_atomic(path, content)

    monkeypatch.setattr(journal, "write_atomic", save_then_cut_over)


def test_a_save_just_before_cutover_is_reported_and_stops_commands(monkeypatch):
    work = old_home_with_work()
    _late_save_before_cutover(monkeypatch, "late.md", "# late\n")

    outcome = migrate.run()

    assert not outcome.done and "exists again" in outcome.messages[0]
    assert "reconcile" in store.outside_error(layout.lemons_dir() / "brief" / work["work"].name)
    with pytest.raises(guard.Paused):
        message_store.send(message_store.inbox_root() / work["inbox"].name, "hi", "tester")


def test_reconcile_brings_the_late_file_in_and_commands_resume(monkeypatch):
    work = old_home_with_work()
    _late_save_before_cutover(monkeypatch, "late.md", "# late\n")
    migrate.run()

    outcome = reconcile.run()

    assert outcome.done, outcome.messages
    assert (layout.lemons_dir() / "brief" / "late.md").read_text() == "# late\n"
    assert not layout.legacy_dir().exists()
    assert not layout.paused()
    message_store.send(message_store.inbox_root() / work["inbox"].name, "hi", "tester")


def test_a_late_file_that_conflicts_is_left_for_a_person(monkeypatch):
    work = old_home_with_work()
    _late_save_before_cutover(monkeypatch, work["work"].name, "# work\n\nStatus: done\n")
    migrate.run()

    outcome = reconcile.run()

    assert not outcome.done and "merge them by hand" in "\n".join(outcome.messages)
    assert (layout.legacy_dir() / work["work"].name).read_text().endswith("done\n")
    assert layout.stray()


def test_reconcile_repoints_an_attachment_an_older_binary_made_in_the_old_home(monkeypatch):
    old_home_with_work()
    _late_save_before_cutover(monkeypatch, "late.md", "# late\n")
    migrate.run()
    late = (layout.legacy_dir() / "late.md").resolve()
    with db.connect() as conn:
        db.add(conn, "claude:old-binary", "", metadata={})
        attached.attach(conn, "claude:old-binary", late)

    assert reconcile.run().done

    with db.connect() as conn:
        path = attached.by_channel(conn, ["claude:old-binary"])["claude:old-binary"]
    assert path == (layout.lemons_dir() / "brief" / "late.md").resolve()


def test_a_reconcile_stopped_after_moving_files_is_finished_by_a_rerun(monkeypatch):
    old_home_with_work()
    _late_save_before_cutover(monkeypatch, "late.md", "# late\n")
    migrate.run()
    late = (layout.legacy_dir() / "late.md").resolve()
    with db.connect() as conn:
        db.add(conn, "claude:old-binary", "", metadata={})
        attached.attach(conn, "claude:old-binary", late)
    bring_in = reconcile._bring_in

    def move_then_crash(old):
        bring_in(old)
        raise KeyboardInterrupt

    monkeypatch.setattr(reconcile, "_bring_in", move_then_crash)
    with pytest.raises(KeyboardInterrupt):
        reconcile.run()
    assert layout.paused() and not layout.legacy_dir().exists()

    monkeypatch.setattr(reconcile, "_bring_in", bring_in)
    outcome = reconcile.run()

    assert outcome.done, outcome.messages
    assert not layout.paused()
    with db.connect() as conn:
        path = attached.by_channel(conn, ["claude:old-binary"])["claude:old-binary"]
    assert path == (layout.lemons_dir() / "brief" / "late.md").resolve()


def test_a_reconcile_stopped_before_moving_resumes_from_its_pause(monkeypatch):
    old_home_with_work()
    _late_save_before_cutover(monkeypatch, "late.md", "# late\n")
    migrate.run()

    repoint = reconcile._repoint

    def crash(old):
        raise KeyboardInterrupt

    monkeypatch.setattr(reconcile, "_repoint", crash)
    with pytest.raises(KeyboardInterrupt):
        reconcile.run()
    monkeypatch.setattr(reconcile, "_repoint", repoint)
    assert layout.paused()

    assert reconcile.run().done
    assert (layout.lemons_dir() / "brief" / "late.md").read_text() == "# late\n"


def test_abort_does_not_lift_a_reconciles_pause(monkeypatch):
    old_home_with_work()
    _late_save_before_cutover(monkeypatch, "late.md", "# late\n")
    migrate.run()
    monkeypatch.setattr(reconcile, "_repoint", lambda old: (_ for _ in ()).throw(KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        reconcile.run()

    assert migrate.abort().paused
    assert layout.paused()


def test_a_symlinked_old_home_after_cutover_is_refused_and_its_target_untouched(tmp_path):
    old_home_with_work()
    assert migrate.run().done
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "keep.md").write_text("# keep\n")
    layout.legacy_dir().symlink_to(unrelated)

    outcome = reconcile.run()

    assert not outcome.done and "is a symlink" in outcome.messages[0]
    assert (unrelated / "keep.md").read_text() == "# keep\n"
    assert not (layout.lemons_dir() / "brief" / "keep.md").exists()
    assert not (layout.lemons_dir() / layout.MIGRATING).exists()


def test_a_resumed_reconcile_refuses_a_path_other_than_the_old_home(tmp_path):
    old_home_with_work()
    assert migrate.run().done
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "keep.md").write_text("# keep\n")
    (layout.lemons_dir() / layout.MIGRATING).write_text(f"reconcile {unrelated}\n")

    outcome = reconcile.run()

    assert not outcome.done and outcome.paused
    assert (unrelated / "keep.md").exists()


def test_a_resumed_reconcile_refuses_an_old_home_that_became_a_symlink(monkeypatch, tmp_path):
    old_home_with_work()
    _late_save_before_cutover(monkeypatch, "late.md", "# late\n")
    migrate.run()
    monkeypatch.setattr(reconcile, "_repoint", lambda old: (_ for _ in ()).throw(KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        reconcile.run()
    unrelated = tmp_path / "unrelated"
    layout.legacy_dir().rename(unrelated)
    layout.legacy_dir().symlink_to(unrelated)

    outcome = reconcile.run()

    assert not outcome.done and "is a symlink" in outcome.messages[0]
    assert (unrelated / "late.md").exists()
