from lemonaid.inbox import db
from lemonaid.tasks.model import associations, holding, ledger

from .shared import new_task
from .test_cli import _run


def _as(monkeypatch, lemon_id: str) -> None:
    monkeypatch.setattr("lemonaid.tasks.cli_common.brief_id", lambda _conn, _name: lemon_id)


def test_observing_instead_of_a_duplicate_closes_it_and_links_the_other(capsys, monkeypatch):
    with db.connect() as conn:
        theirs = new_task(conn, brief_id="Author.one", request_id="theirs")
        mine = new_task(conn, brief_id="Review.one", request_id="mine")
    _as(monkeypatch, "Review.one")

    done = _run(capsys, "observe", theirs, "--instead-of", mine, "--json")
    again = _run(capsys, "observe", theirs, "--instead-of", mine, "--json")

    with db.connect() as conn:
        assert ledger.state(conn, mine)["lifecycle"] == "closed"
        assert theirs in associations.observed_of(conn, "Review.one")
    assert done["error"] is None and again == done


def test_a_brief_that_handed_its_task_on_can_observe_it(capsys, monkeypatch):
    with db.connect() as conn:
        task = new_task(conn, brief_id="Review.one")
        with ledger.transaction(conn):
            holding.assign(conn, task, 1, "brief:Author.one", "back", False, "Review.one", "a", 2.0)
    _as(monkeypatch, "Review.one")

    done = _run(capsys, "observe", task, "--json")

    with db.connect() as conn:
        assert associations.observed_of(conn, "Review.one") == [task]
    assert done["error"] is None and done["holder"] == "brief:Author.one"


def test_only_an_open_task_the_caller_holds_can_be_retired(capsys, monkeypatch):
    with db.connect() as conn:
        theirs = new_task(conn, brief_id="Author.one", request_id="theirs")
        other = new_task(conn, brief_id="Someone.else", request_id="other")
    _as(monkeypatch, "Review.one")

    refused = _run(capsys, "observe", theirs, "--instead-of", other, "--json")
    itself = _run(capsys, "observe", theirs, "--instead-of", theirs, "--json")

    with db.connect() as conn:
        assert ledger.state(conn, other)["lifecycle"] == "open"
        assert ledger.state(conn, theirs)["lifecycle"] == "open"
    assert "isn't an open task you hold" in refused["error"]
    assert "duplicate of itself" in itself["error"]


def test_an_observer_can_stop_observing_but_the_holder_cant(capsys, monkeypatch):
    with db.connect() as conn:
        task = new_task(conn, brief_id="Author.one")
        with ledger.transaction(conn):
            associations.observe(conn, task, 1, "Review.one", "Review.one", "o", 1.0)

    _as(monkeypatch, "Review.one")
    stopped = _run(capsys, "unobserve", task, "--json")
    _as(monkeypatch, "Author.one")
    refused = _run(capsys, "unobserve", task, "--json")

    with db.connect() as conn:
        assert associations.observed_of(conn, "Review.one") == []
        assert ledger.consistent(conn, task)
    assert stopped["error"] is None and "doesn't observe" in refused["error"]
