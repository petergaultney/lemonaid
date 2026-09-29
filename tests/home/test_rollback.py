from lemonaid.brief import store
from lemonaid.home import layout, migrate, rollback
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
    message_store.send(message_store.inbox_for_id(work["inbox"].name), "New", "tester")

    outcome = rollback.run()

    assert not outcome.done
    assert "added after the migration" in outcome.messages[0]
