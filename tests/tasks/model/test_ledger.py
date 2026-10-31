import pytest

from lemonaid.inbox import db
from lemonaid.tasks.model import holding, ledger, lifecycle

from ..shared import new_task


def _assign(conn, task, expected, to, request_id):
    with ledger.transaction(conn):
        return ledger.once(
            conn,
            request_id,
            {"op": "assign", "task": task, "to": to},
            lambda: holding.assign(
                conn, task, expected, to, "", True, "Work.alpha", request_id, 200.0
            ),
        )


def test_concurrent_transfers_from_one_revision_have_one_winner():
    with db.connect() as conn:
        task = new_task(conn)
        _assign(conn, task, 1, "brief:Work.bravo", "r1")

        with pytest.raises(ledger.Conflict) as caught:
            _assign(conn, task, 1, "brief:Work.charlie", "r2")

        assert caught.value.current["holder"] == "brief:Work.bravo"
        assert ledger.state(conn, task)["previous_holder"] == "brief:Work.alpha"


def test_a_stale_revision_fails_even_after_the_holder_returns():
    with db.connect() as conn:
        task = new_task(conn)
        _assign(conn, task, 1, "brief:Work.bravo", "r1")
        _assign(conn, task, 2, "brief:Work.alpha", "r2")

        with pytest.raises(ledger.Conflict):
            _assign(conn, task, 1, "brief:Work.charlie", "r3")


def test_a_repeated_request_returns_its_original_result_and_a_reused_one_is_refused():
    with db.connect() as conn:
        task = new_task(conn)
        first = _assign(conn, task, 1, "brief:Work.bravo", "r1")

        assert _assign(conn, task, 1, "brief:Work.bravo", "r1") == first
        assert ledger.state(conn, task)["revision"] == 2
        with pytest.raises(ledger.RequestReused):
            _assign(conn, task, 1, "brief:Work.charlie", "r1")


def test_a_failed_operation_leaves_no_event_and_no_request_record():
    with db.connect() as conn:
        task = new_task(conn)
        with pytest.raises(ValueError):
            _assign(conn, task, 1, "nobody", "r1")

        assert len(ledger.history(conn, task)) == 1
        assert _assign(conn, task, 1, "brief:Work.bravo", "r1")["revision"] == 2


def test_replaying_events_reproduces_the_current_state():
    with db.connect() as conn:
        task = new_task(conn)
        _assign(conn, task, 1, "brief:Work.bravo", "r1")
        with ledger.transaction(conn):
            lifecycle.set_url(
                conn, task, 2, "https://example.com/pr/2", "successor", "x", "r2", 300.0
            )

        assert ledger.consistent(conn, task)
        conn.execute("UPDATE tasks SET holder = 'brief:Other.one' WHERE task_id = ?", (task,))
        assert not ledger.consistent(conn, task)
