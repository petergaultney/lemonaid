import argparse
import contextlib
import json

from lemonaid.inbox import db
from lemonaid.messages import store
from lemonaid.tasks import cli, cli_common
from lemonaid.tasks.model import dependencies, ledger

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
