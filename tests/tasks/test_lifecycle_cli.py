import argparse
import contextlib
import json

from lemonaid.inbox import db
from lemonaid.messages import store
from lemonaid.tasks import cli, cli_common
from lemonaid.tasks.inspection import task_input
from lemonaid.tasks.model import dependencies, holding, ledger

from .shared import new_task


def _run(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["task", *argv, "--json"])
    with contextlib.suppress(SystemExit):
        args.func(args)

    return json.loads(capsys.readouterr().out)


def _told(lemon_id: str) -> list[str]:
    return [p.read_text() for p in store.mailbox_for_id(lemon_id).glob("*.md")]


def _family(conn) -> tuple[str, str]:
    """A lead's task waiting for a child's task."""
    parent = new_task(conn, brief_id="Lead.lead", sponsor="")
    child = new_task(conn, brief_id="Child.one", sponsor="Lead.lead", request_id="child")
    with ledger.transaction(conn):
        dependencies.depend(conn, parent, 1, child, "Lead.lead", "dep", 1.0)
    return parent, child


def test_closing_a_task_releases_its_waiting_parent_and_tells_both_holders(capsys):
    with db.connect() as conn:
        parent, child = _family(conn)

    closed = _run(capsys, "close", child, "--reason", "done elsewhere")

    with db.connect() as conn:
        assert ledger.state(conn, child)["lifecycle"] == "closed"
        assert dependencies.waits_for(conn, parent) == []
        assert ledger.consistent(conn, parent) and ledger.consistent(conn, child)
    assert closed["released"] == [parent]
    assert "is now closed" in _told("Child.one")[0]
    assert "Pick up its result" in _told("Lead.lead")[0]


def test_the_holder_closing_its_own_task_isnt_told(capsys, monkeypatch):
    with db.connect() as conn:
        made = new_task(conn)
    monkeypatch.setattr(cli_common, "actor", lambda _conn: "Work.alpha")

    _run(capsys, "close", made, "--reason", "finished")
    again = _run(capsys, "close", made, "--reason", "finished")
    reopened = _run(capsys, "reopen", made, "--reason", "not quite")

    assert "already closed" in again["error"]
    assert reopened["holder"] == "brief:Work.alpha"
    assert not store.mailbox_for_id("Work.alpha").exists()


def test_a_result_needs_evidence_and_leaves_the_task_open(capsys):
    with db.connect() as conn:
        made = new_task(conn)

    empty = _run(capsys, "result", made, "--evidence", " ")
    recorded = _run(capsys, "result", made, "--evidence", "https://example.com/pr/9")

    assert "needs evidence" in empty["error"]
    with db.connect() as conn:
        assert ledger.state(conn, made)["lifecycle"] == "open"
        assert ledger.history(conn, made)[-1]["data"] == {"evidence": "https://example.com/pr/9"}
    assert recorded["revision"] == 2


def test_wait_until_records_a_time_that_a_later_one_replaces_and_a_past_one_is_refused(capsys):
    with db.connect() as conn:
        made = new_task(conn)

    first = _run(capsys, "wait-until", made, "2h", "--reason", "launch window")
    second = _run(capsys, "wait-until", made, "3h", "--reason", "cooldown")
    past = _run(capsys, "wait-until", made, "2020-01-01T00:00:00+00:00", "--reason", "x")
    unparsed = _run(capsys, "wait-until", made, "soon", "--reason", "x")

    assert first["error"] is None and second["until"] > first["until"]
    assert "already passed" in past["error"]
    assert "neither a duration" in unparsed["error"]
    with db.connect() as conn:
        assert ledger.state(conn, made)["revision"] == 3
        assert ledger.consistent(conn, made)
        [latest] = [e for e in ledger.history(conn, made) if e["kind"] == "wait_until"][-1:]
        assert latest["data"]["reason"] == "cooldown"


def test_a_time_wait_reaches_the_checker_only_for_the_assignment_that_declared_it(capsys):
    with db.connect() as conn:
        made = new_task(conn)
    _run(capsys, "wait-until", made, "2h", "--reason", "launch window")

    with db.connect() as conn:
        waiting = task_input.fields(conn, ledger.state(conn, made), {})
    with db.connect() as conn:
        with ledger.transaction(conn):
            holding.assign(conn, made, 2, "brief:Work.bravo", "", True, "Work.alpha", "a1", 9e9)
        after = task_input.fields(conn, ledger.state(conn, made), {})

    assert waiting["wait_until.reason"] == "launch window"
    assert "wait_until.at" not in after


def test_a_repeated_wait_until_duration_with_one_request_id_returns_the_first_deadline(capsys):
    with db.connect() as conn:
        made = new_task(conn)

    first = _run(capsys, "wait-until", made, "2h", "--reason", "x", "--request-id", "same")
    again = _run(capsys, "wait-until", made, "2h", "--reason", "x", "--request-id", "same")

    assert first["error"] is None and again == first
    with db.connect() as conn:
        assert ledger.state(conn, made)["revision"] == 2
