from lemonaid.brief import store
from lemonaid.home import copying, layout, migrate, rollback
from lemonaid.messages import store as message_store

from .shared import db_paths, old_home_with_work


def test_a_rollback_with_nothing_changed_restores_the_old_home():
    work = old_home_with_work()
    before = db_paths()
    assert migrate.run().done

    outcome = rollback.run()

    assert outcome.done, outcome.messages
    assert db_paths() == before
    assert work["work"].read_text().startswith("# work")
    assert work["read"].exists()
    assert store.briefs_dir() == layout.legacy_dir()
    assert not list((layout.lemons_dir() / "brief").rglob("*.md"))


def test_a_rollback_refuses_after_a_brief_is_edited():
    old_home_with_work()
    assert migrate.run().done
    edited = layout.lemons_dir() / "brief" / "2026-09-01-work.md"
    edited.write_text("# work\n\nStatus: done\n")

    outcome = rollback.run()

    assert not outcome.done
    assert "changed after the migration" in outcome.messages[0]
    assert layout.cut_over()
    assert edited.read_text().endswith("done\n")


def test_a_rollback_refuses_after_a_message_arrives():
    work = old_home_with_work()
    assert migrate.run().done
    message_store.send(message_store.mailbox_for_id(work["mailbox"].name), "New", "tester")

    outcome = rollback.run()

    assert not outcome.done
    assert "added after the migration" in outcome.messages[0]


def _as_an_older_lemonaid_left_it() -> None:
    (layout.lemons_dir() / "mailbox").rename(layout.lemons_dir() / "inbox")


def test_a_rollback_restores_a_home_an_older_lemonaid_migrated():
    work = old_home_with_work()
    assert migrate.run().done
    _as_an_older_lemonaid_left_it()

    outcome = rollback.run()

    assert outcome.done, outcome.messages
    assert work["read"].exists()
    assert not (layout.lemons_dir() / "inbox").is_symlink()


def test_a_migration_an_older_lemonaid_stopped_finishes(monkeypatch):
    work = old_home_with_work()
    copy_all = copying.copy_all
    monkeypatch.setattr(copying, "copy_all", lambda record: copy_all(record) or "stopped")
    assert not migrate.run().done
    _as_an_older_lemonaid_left_it()
    monkeypatch.setattr(copying, "copy_all", copy_all)

    outcome = migrate.run()

    assert outcome.done, outcome.messages
    assert message_store.take_next(message_store.mailbox_for_id(work["mailbox"].name))
