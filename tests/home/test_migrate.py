import os
from pathlib import Path

import pytest

from lemonaid.brief import attached, store
from lemonaid.home import copying, inventory, layout, migrate
from lemonaid.inbox import db
from lemonaid.messages import store as message_store
from lemonaid.messages import waiter

from .shared import db_paths, old_home_with_work


def _new(path: Path) -> Path:
    return inventory.destination(
        layout.legacy_dir().resolve(),
        path.resolve().relative_to(layout.legacy_dir().resolve()).as_posix(),
    )


def test_a_migration_moves_briefs_messages_and_db_paths_and_keeps_a_backup():
    work = old_home_with_work()
    texts = {name: path.read_bytes() for name, path in work.items() if path.is_file()}

    outcome = migrate.run()

    assert outcome.done, outcome.messages
    assert layout.cut_over()
    assert not layout.legacy_dir().exists()
    for name, text in texts.items():
        assert _new(work[name]).read_bytes() == text, name
    assert all(p.startswith(str(layout.lemons_dir().resolve() / "brief")) for p in db_paths())
    with db.connect() as conn:
        assert attached.by_channel(conn, ["claude:work"])["claude:work"] == _new(work["work"])
    [backup] = (layout.lemons_dir() / "migrations").iterdir()
    assert (backup / "brief-lemons" / work["work"].name).read_bytes() == texts["work"]
    assert (backup / "lemonaid.db").exists()
    assert store.briefs_dir() == layout.lemons_dir() / "brief"
    assert message_store.inbox_root() == layout.lemons_dir() / "inbox"
    assert message_store.take_next(message_store.inbox_for_id(work["inbox"].name))[1].endswith(
        "Unread\n"
    )


def test_blockers_refuse_the_migration_and_change_nothing():
    work = old_home_with_work()
    (layout.legacy_dir() / "sneaky.md").symlink_to(work["work"])
    os.mkfifo(layout.legacy_dir() / "pipe")
    taken = _new(work["waiting"])
    taken.parent.mkdir(parents=True)
    taken.write_text("someone else's\n")
    before = db_paths()

    with waiter.armed(work["inbox"]):
        outcome = migrate.run()

    assert not outcome.done and not outcome.paused
    text = "\n".join(outcome.messages)
    for expected in ("is a symlink", "not a regular file", "already exists", "waiter is armed"):
        assert expected in text
    assert db_paths() == before
    assert not (layout.lemons_dir() / layout.MIGRATING).exists()
    assert not layout.cut_over()
    assert taken.read_text() == "someone else's\n"


def test_a_db_path_to_a_missing_file_blocks_the_migration():
    work = old_home_with_work()
    work["waiting"].unlink()

    outcome = migrate.run()

    assert "does not exist" in "\n".join(outcome.messages)
    assert work["work"].exists()


def test_a_brief_saved_during_the_copy_stops_it_paused_and_abort_restores(monkeypatch):
    work = old_home_with_work()
    before = db_paths()
    copy = copying.copy_all

    def copy_then_save(record):
        error = copy(record)
        work["work"].write_text("# work\n\nStatus: done\n")  # an editor's save
        return error

    monkeypatch.setattr(copying, "copy_all", copy_then_save)
    stopped = migrate.run()

    assert stopped.paused and "changed after the inventory" in "\n".join(stopped.messages)
    assert layout.paused()
    assert db_paths() == before

    aborted = migrate.abort()

    assert not aborted.paused
    assert not layout.paused()
    assert work["work"].read_text() == "# work\n\nStatus: done\n"
    assert not _new(work["work"]).exists()
    assert store.briefs_dir() == layout.legacy_dir()


def test_a_crash_after_the_db_rewrite_finishes_on_rerun(monkeypatch):
    work = old_home_with_work()
    rename = os.rename

    def crash(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(migrate.os, "rename", crash)
    with pytest.raises(KeyboardInterrupt):
        migrate.run()
    assert layout.paused()
    assert layout.legacy_dir().exists()

    monkeypatch.setattr(migrate.os, "rename", rename)
    outcome = migrate.run()

    assert outcome.done, outcome.messages
    assert _new(work["work"]).exists()
    assert not layout.paused()


def test_an_old_home_recreated_after_the_move_keeps_the_migration_paused(monkeypatch):
    old_home_with_work()
    rename = os.rename

    def rename_then_recreate(source, target):
        rename(source, target)
        Path(source).mkdir()  # an old binary writing a brief or message

    monkeypatch.setattr(migrate.os, "rename", rename_then_recreate)
    outcome = migrate.run()

    assert outcome.paused and "was recreated" in "\n".join(outcome.messages)
    assert not (layout.lemons_dir() / layout.CUTOVER).exists()
    assert layout.paused()


def test_a_second_migration_is_refused():
    old_home_with_work()
    assert migrate.run().done

    assert migrate.run().messages == ["Already migrated"]


def test_a_pause_stops_waiters_arming_and_the_migration_continues_from_it():
    work = old_home_with_work()
    assert migrate.pause().paused

    with pytest.raises(ValueError, match="migration is in progress"):
        message_store.inbox_for_id(work["inbox"].name)

    outcome = migrate.run()

    assert outcome.done, outcome.messages
    assert not layout.paused()


def test_a_blocker_after_a_pause_keeps_the_pause():
    work = old_home_with_work()
    migrate.pause()

    with waiter.armed(work["inbox"]):
        outcome = migrate.run()

    assert outcome.paused and "waiter is armed" in "\n".join(outcome.messages)
    assert layout.paused()
    assert not migrate.abort().paused
