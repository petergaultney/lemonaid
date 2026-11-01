import argparse

import lemonaid.tasks.cli
import lemonaid.tasks.cli_common
from lemonaid.brief import verbs_cli
from lemonaid.inbox import db
from lemonaid.tasks.model import holding, ledger

from .test_options_cli import _PARENT, _attached, _enabled, _parsed  # noqa: F401


def _child(capsys) -> dict:
    child = _attached(capsys, "Finish me")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO lemon_parents (lemon_id, parent_id, linked_at) VALUES (?, ?, 0)",
            (child["lemon_id"], _PARENT),
        )
        conn.commit()
    return child


def _done(capsys) -> dict:
    parser = argparse.ArgumentParser()
    verbs_cli.add_parsers(parser.add_subparsers())
    return _parsed(capsys, parser, ["status", "--channel", "claude:worker", "done", "--json"])


def _close(capsys, task: str, *extra: str) -> dict:
    parser = argparse.ArgumentParser()
    lemonaid.tasks.cli.setup_parser(parser.add_subparsers())
    argv = ["task", "close", task, "--reason", "finished", *extra, "--json"]
    return _parsed(capsys, parser, argv)


def test_done_hands_the_task_to_the_parent_to_check(capsys):
    child = _child(capsys)

    done = _done(capsys)

    with db.connect() as conn:
        state = ledger.state(conn, child["task_id"])
        last = ledger.history(conn, child["task_id"])[-1]
    assert done["error"] is None
    assert (state["lifecycle"], state["holder"]) == ("check", f"brief:{_PARENT}")
    assert (last["actor"], last["data"]["reason"]) == (
        child["lemon_id"],
        "says this is done; check the work",
    )


def test_the_holder_of_a_task_awaiting_its_check_may_close_it_despite_its_own_parent(
    capsys, monkeypatch
):
    child = _child(capsys)
    _done(capsys)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO lemon_parents (lemon_id, parent_id, linked_at) VALUES (?, 'Top.hq', 0)",
            (_PARENT,),
        )
        conn.commit()
    monkeypatch.setattr(lemonaid.tasks.cli_common, "actor", lambda _conn, channel="": _PARENT)

    closed = _close(capsys, child["task_id"], "--request-id", "checked")
    retried = _close(capsys, child["task_id"], "--request-id", "checked")

    with db.connect() as conn:
        state = ledger.state(conn, child["task_id"])
    assert closed["error"] is None and state["lifecycle"] == "closed"
    assert retried == closed


def test_a_holder_with_a_parent_cant_close_its_own_task_but_a_human_can(capsys, monkeypatch):
    child = _child(capsys)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:worker")

    refused = _close(capsys, child["task_id"])
    monkeypatch.delenv("LEMONAID_CHANNEL")
    closed = _close(capsys, child["task_id"])

    assert "mark your brief done" in refused["error"]
    with db.connect() as conn:
        state = ledger.state(conn, child["task_id"])
    assert closed["error"] is None and state["lifecycle"] == "closed"


def test_handing_a_task_back_from_its_check_reopens_the_work(capsys):
    child = _child(capsys)
    _done(capsys)
    with db.connect() as conn, ledger.transaction(conn):
        state = ledger.state(conn, child["task_id"])
        holding.assign(
            conn,
            child["task_id"],
            state["revision"],
            f"brief:{child['lemon_id']}",
            "the tests fail",
            False,
            _PARENT,
            "back",
            2.0,
        )

    with db.connect() as conn:
        assert ledger.state(conn, child["task_id"])["lifecycle"] == "open"
