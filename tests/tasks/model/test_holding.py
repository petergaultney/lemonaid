import pytest

from lemonaid.inbox import db
from lemonaid.tasks.model import holding, ids, ledger, lifecycle

from ..shared import new_task


def test_url_can_be_added_and_replaced_without_changing_task_identity():
    with db.connect() as conn:
        task = new_task(conn)
        with ledger.transaction(conn):
            lifecycle.set_url(
                conn, task, 1, "https://example.com/pr/1", "PR opened", "x", "r1", 1.0
            )
            replaced = lifecycle.set_url(
                conn, task, 2, "https://example.com/pr/2", "successor PR", "x", "r2", 2.0
            )

        assert replaced["previous_url"] == "https://example.com/pr/1"
        assert ledger.state(conn, task)["subject_url"] == "https://example.com/pr/2"
        assert [e["data"].get("previous") for e in ledger.history(conn, task)[1:]] == [
            "",
            "https://example.com/pr/1",
        ]


@pytest.mark.parametrize("url, reason", [("not a url", "why"), ("https://example.com", " ")])
def test_url_change_needs_an_absolute_url_and_a_reason(url, reason):
    with db.connect() as conn:
        task = new_task(conn)
        with pytest.raises(ValueError), ledger.transaction(conn):
            lifecycle.set_url(conn, task, 1, url, reason, "x", "r1", 1.0)


def test_attachment_starts_the_clock_once_and_follows_a_reroll():
    with db.connect() as conn:
        task = new_task(conn)
        conn.execute(
            "INSERT INTO lemon_aliases (old_id, lemon_id) VALUES ('Work.alpha', 'New.alpha')"
        )
        conn.commit()
        with ledger.transaction(conn):
            assert holding.attach(conn, "New.alpha", "hook", 150.0) == [task]
        with ledger.transaction(conn):
            assert holding.attach(conn, "New.alpha", "hook", 160.0) == []

        assert ledger.state(conn, task)["attached_at"] == 150.0
        assert [t["task_id"] for t in holding.held_by(conn, "Work.alpha")] == [task]


def test_held_by_leaves_out_closed_tasks():
    with db.connect() as conn:
        task = new_task(conn)
        assert [t["task_id"] for t in holding.held_by(conn, "Work.alpha")] == [task]

        conn.execute("UPDATE tasks SET lifecycle = 'closed' WHERE task_id = ?", (task,))
        assert holding.held_by(conn, "Work.alpha") == []


@pytest.mark.parametrize("text", ["", "alpha", "robot:x", "brief:", "human:sam", "external:ci"])
def test_holder_must_be_tagged(text):
    with pytest.raises(ValueError):
        ids.holder(text)


def test_assigning_a_closed_task_keeps_it_closed():
    with db.connect() as conn:
        task = new_task(conn)
        with ledger.transaction(conn):
            lifecycle.close(conn, task, 1, "finished", "x", "close", 1.0)
            holding.assign(
                conn, task, 2, "brief:Other.one", "move the record", False, "x", "a", 2.0
            )

        assert ledger.state(conn, task)["lifecycle"] == "closed"
