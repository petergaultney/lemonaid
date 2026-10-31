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
            assert holding.attach(conn, "New.alpha", "hook", 50.0) == [task]
        with ledger.transaction(conn):
            assert holding.attach(conn, "New.alpha", "hook", 60.0) == []

        assert ledger.state(conn, task)["attached_at"] == 50.0
        assert [t["task_id"] for t in holding.held_by(conn, "Work.alpha")] == [task]


def test_held_by_includes_tasks_the_brief_answers_for_and_leaves_out_closed_ones():
    with db.connect() as conn:
        task = new_task(conn)
        other = new_task(conn, brief_id="Work.bravo")
        conn.execute(
            "UPDATE tasks SET holder = 'human:sam', accountable_brief_id = 'Work.alpha'"
            " WHERE task_id = ?",
            (other,),
        )
        assert [t["task_id"] for t in holding.held_by(conn, "Work.alpha")] == [task, other]

        conn.execute("UPDATE tasks SET lifecycle = 'closed' WHERE task_id = ?", (task,))
        assert [t["task_id"] for t in holding.held_by(conn, "Work.alpha")] == [other]


@pytest.mark.parametrize("text", ["", "alpha", "robot:x", "brief:"])
def test_holder_must_be_tagged(text):
    with pytest.raises(ValueError):
        ids.holder(text)
