"""The migration's refusals and recovery for interrupted copies, symlinks, and races."""

import contextlib
import os
import shutil
import threading
import time

import pytest

from lemonaid.home import copying, guard, layout, migrate, rollback
from lemonaid.messages import store as message_store

from .shared import db_paths, old_home_with_work


def test_a_copy_interrupted_part_way_is_finished_by_a_rerun(monkeypatch):
    work = old_home_with_work()
    copyfileobj = shutil.copyfileobj
    calls = []

    def fail_second(reader, writer):
        calls.append(1)
        if len(calls) == 2:
            writer.write(reader.read(3))  # some bytes, then the disk fills
            raise OSError("No space left on device")
        copyfileobj(reader, writer)

    monkeypatch.setattr(copying.shutil, "copyfileobj", fail_second)
    with contextlib.suppress(OSError):
        migrate.run()
    assert layout.paused()
    partials = list(layout.lemons_dir().rglob("*.lemonaid-migrate-*.tmp"))
    assert partials, "the interrupted file is left only under its partial name"

    monkeypatch.setattr(copying.shutil, "copyfileobj", copyfileobj)
    outcome = migrate.run()

    assert outcome.done, outcome.messages
    assert not list(layout.lemons_dir().rglob("*.lemonaid-migrate-*.tmp"))
    assert (layout.lemons_dir() / "brief" / work["work"].name).read_text().startswith("# work")


def test_abort_after_an_interrupted_copy_leaves_nothing_behind(monkeypatch):
    old_home_with_work()
    before = db_paths()
    copyfileobj = shutil.copyfileobj

    def fail(reader, writer):
        writer.write(b"par")
        raise OSError("interrupted")

    monkeypatch.setattr(copying.shutil, "copyfileobj", fail)
    with contextlib.suppress(OSError):
        migrate.run()

    assert not migrate.abort().paused
    assert not [
        p for p in layout.lemons_dir().rglob("*") if p.is_file() and "migrations" not in p.parts
    ]
    assert db_paths() == before
    monkeypatch.setattr(copying.shutil, "copyfileobj", copyfileobj)
    assert migrate.run().done


def test_a_symlinked_destination_directory_refuses_the_migration(tmp_path):
    work = old_home_with_work()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    layout.lemons_dir().mkdir()
    (layout.lemons_dir() / "inbox").symlink_to(elsewhere)

    outcome = migrate.run()

    assert not outcome.done
    assert any("is a symlink" in m for m in outcome.messages)
    assert not any(elsewhere.iterdir())
    assert work["work"].exists()


def test_a_destination_symlink_made_after_planning_stops_before_cutover(monkeypatch, tmp_path):
    old_home_with_work()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    rename = os.rename

    def rename_then_redirect(source, target):
        rename(source, target)
        brief = layout.lemons_dir() / "brief"
        rename(brief, elsewhere / "brief")
        brief.symlink_to(elsewhere / "brief")

    monkeypatch.setattr(migrate.os, "rename", rename_then_redirect)
    outcome = migrate.run()

    assert outcome.paused and any("is a symlink" in m for m in outcome.messages)
    assert not (layout.lemons_dir() / layout.CUTOVER).exists()


def test_a_symlinked_old_home_is_refused(tmp_path):
    real = tmp_path / "real-briefs"
    real.mkdir()
    (real / "a.md").write_text("# a\n")
    layout.legacy_dir().symlink_to(real)

    outcome = migrate.run()

    assert not outcome.done and "is a symlink" in "\n".join(outcome.messages)
    assert (real / "a.md").exists()
    assert layout.legacy_dir().is_symlink()


def test_a_file_written_to_the_old_home_after_the_recheck_stops_before_cutover(monkeypatch):
    old_home_with_work()
    rename = os.rename

    def write_then_rename(source, target):
        (layout.legacy_dir() / "late.md").write_text("# late\n")  # an old binary's brief
        rename(source, target)

    monkeypatch.setattr(migrate.os, "rename", write_then_rename)
    outcome = migrate.run()

    assert outcome.paused and "after the inventory" in "\n".join(outcome.messages)
    assert not layout.cut_over()


def test_rollback_waits_for_a_send_already_under_way_and_then_refuses():
    work = old_home_with_work()
    assert migrate.run().done
    inbox = message_store.inbox_root() / work["inbox"].name
    in_flight = threading.Event()

    def slow_send():  # `tell -` still reading its stdin when the pause starts
        with guard.operation():
            in_flight.set()
            time.sleep(0.3)
            message_store._write(inbox, "Sent while rollback paused", "tester")

    sender = threading.Thread(target=slow_send)
    sender.start()
    in_flight.wait()
    outcome = rollback.run()
    sender.join()

    assert not outcome.done and "added after the migration" in outcome.messages[0]
    assert not layout.paused()
    assert layout.cut_over()
    assert any("while rollback paused" in p.read_text() for p in inbox.glob("*.md"))


def test_a_send_after_the_pause_is_refused_rather_than_written():
    work = old_home_with_work()
    assert migrate.run().done
    inbox = message_store.inbox_root() / work["inbox"].name
    (layout.lemons_dir() / layout.MIGRATING).write_text("x\n")

    with pytest.raises(guard.Paused):
        message_store.send(inbox, "late", "tester")

    assert not any(p.read_text().endswith("late\n") for p in inbox.glob("*.md"))


def test_files_with_partial_looking_names_that_the_migration_did_not_write_survive(monkeypatch):
    work = old_home_with_work()
    brief_dir = layout.lemons_dir() / "brief"
    brief_dir.mkdir(parents=True)
    bystander = brief_dir / f".{work['work'].name}.lemonaid-migrate-19990101T000000Z.tmp"
    bystander.write_text("someone else's\n")

    def fail(reader, writer):
        writer.write(b"par")
        raise OSError("interrupted")

    monkeypatch.setattr(copying.shutil, "copyfileobj", fail)
    with contextlib.suppress(OSError):
        migrate.run()
    migrate.abort()

    assert bystander.read_text() == "someone else's\n"


def test_rollback_keeps_the_copies_it_takes_out_of_the_new_home():
    work = old_home_with_work()
    assert migrate.run().done

    assert rollback.run().done

    [journal_dir] = (layout.lemons_dir() / "migrations").iterdir()
    assert (journal_dir / "rolled-back" / work["work"].name).read_text().startswith("# work")


def test_a_symlinked_new_home_refuses_rollback(tmp_path):
    work = old_home_with_work()
    assert migrate.run().done
    inbox = layout.lemons_dir() / "inbox"
    shutil.move(inbox, tmp_path / "moved-inbox")
    inbox.symlink_to(tmp_path / "moved-inbox")

    outcome = rollback.run()

    assert not outcome.done and "is a symlink" in outcome.messages[0]
    assert (tmp_path / "moved-inbox" / work["inbox"].name).is_dir()
