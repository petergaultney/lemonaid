import pytest

from lemonaid.inbox import db
from lemonaid.tasks.model import associations, dependencies, holding, ledger

from ..shared import new_task


def _depend(conn, parent, child):
    with ledger.transaction(conn):
        revision = ledger.state(conn, parent)["revision"]
        return dependencies.depend(conn, parent, revision, child, "x", f"dep-{parent}-{child}", 1.0)


def test_a_brief_that_holds_tasks_cant_be_exempt_but_an_exempt_one_can_take_tasks():
    with db.connect() as conn:
        task = new_task(conn)
        with pytest.raises(ledger.Refused), ledger.transaction(conn):
            associations.exempt(conn, "Work.alpha", "on call", "", 1.0)
        second = new_task(conn, request_id="again")

        with ledger.transaction(conn):
            associations.exempt(conn, "Lead.lead", "coordinates the area", "", 1.0)
        led = new_task(conn, brief_id="Lead.lead")

        assert associations.held_of(conn, "Work.alpha") == [task, second]
        assert associations.exemption_of(conn, "Lead.lead") == "coordinates the area"
        assert associations.held_of(conn, "Lead.lead") == [led]


def test_an_observer_leaves_the_holder_alone_until_it_takes_the_task():
    with db.connect() as conn:
        task = new_task(conn)
        with ledger.transaction(conn):
            associations.observe(conn, task, 1, "Watch.one", "x", "r1", 1.0)

        assert associations.held_of(conn, "Watch.one") == []
        assert associations.observed_of(conn, "Watch.one") == [task]
        assert ledger.state(conn, task)["holder"] == "brief:Work.alpha"

        with ledger.transaction(conn):
            holding.assign(conn, task, 2, "brief:Watch.one", "", False, "Watch.one", "r2", 2.0)

        assert associations.links_of(conn, task) == [
            {"brief_id": "Work.alpha", "kind": "observer"},
            {"brief_id": "Watch.one", "kind": "holder"},
        ]
        assert ledger.consistent(conn, task)


def test_a_dependency_cycle_is_refused_with_the_whole_loop():
    with db.connect() as conn:
        a, b, c = new_task(conn), new_task(conn, brief_id="B.b"), new_task(conn, brief_id="C.c")
        _depend(conn, a, b)
        _depend(conn, b, c)

        with pytest.raises(ledger.Refused, match="cycle") as caught:
            _depend(conn, c, a)
        assert str(caught.value).count("task:") == 4
        with pytest.raises(ledger.Refused):
            _depend(conn, a, a)
        assert ledger.consistent(conn, a)
