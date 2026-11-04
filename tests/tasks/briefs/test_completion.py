import argparse

import pytest

import lemonaid.tasks.cli
import lemonaid.tasks.cli_common
from lemonaid.brief import archive, attached, identity, lemon, verbs_cli
from lemonaid.brief.store import briefs_dir as store_dir
from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.messages import store
from lemonaid.tasks.briefs import notices, planning, registration
from lemonaid.tasks.model import associations, holding, ledger

from ..shared import new_task
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


def test_done_hands_the_task_to_the_parent_to_check(capsys, dead):
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
    capsys, monkeypatch, dead
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


def test_a_holder_with_a_parent_closes_its_own_finished_task(capsys, monkeypatch, dead):
    child = _child(capsys)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:worker")

    closed = _close(capsys, child["task_id"])

    with db.connect() as conn:
        state = ledger.state(conn, child["task_id"])
    assert closed["error"] is None and state["lifecycle"] == "closed"


def test_handing_a_task_back_from_its_check_reopens_the_work(capsys, dead):
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


def test_done_skips_a_parent_that_isnt_live_for_the_nearest_live_ancestor(capsys, dead):
    child = _child(capsys)
    with db.connect() as conn:
        links.set_parent(conn, _PARENT, "Top.hq")
    dead.add(_PARENT)

    _done(capsys)

    with db.connect() as conn:
        assert ledger.state(conn, child["task_id"])["holder"] == "brief:Top.hq"


def test_done_is_refused_while_no_ancestor_is_live(capsys, dead):
    child = _child(capsys)
    dead.add(_PARENT)

    refused = _done(capsys)

    assert f"{_PARENT} isn't live" in refused["error"]
    with db.connect() as conn:
        assert ledger.state(conn, child["task_id"])["holder"] == f"brief:{child['lemon_id']}"


def test_registering_a_task_for_another_running_brief_tells_it(tmp_path):
    path = tmp_path / "briefs" / "2026-11-02-busy.md"
    path.write_text("# Busy\n\nLemon-ID: busy.Worker\n")
    plan = planning.Plan(mode="new", actor=_PARENT, attached=True)
    with db.connect() as conn:
        identity.ensure(conn, path)
        recorded = registration.register(conn, plan, "busy.Worker", _PARENT, "More work", 5.0)
        said = notices.notice(conn, recorded, _PARENT)

    [message] = store.mailbox_for_id("busy.Worker").glob("*.md")
    assert "has been told" in said
    assert f"You now hold task:{recorded['task_id']}" in message.read_text()


def _registered(name: str) -> str:
    path = store_dir() / f"2026-11-02-{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n")
    with db.connect() as conn:
        return identity.ensure(conn, path)


def test_archiving_a_brief_hands_its_open_tasks_to_its_parent(dead):
    lead, child = _registered("lead"), _registered("child")
    with db.connect() as conn:
        links.set_parent(conn, child, lead)
        task = new_task(conn, brief_id=child, sponsor="")
        archive.archive(conn, lemon.brief_of(conn, child), 0.0)

        assert ledger.state(conn, task)["holder"] == f"brief:{lead}"
        assert associations.observed_of(conn, child) == [task]


def test_a_task_with_no_one_to_go_to_stops_its_brief_being_archived(dead):
    alone = _registered("alone")
    with db.connect() as conn:
        task = new_task(conn, brief_id=alone, sponsor="")

        with pytest.raises(ValueError, match="no live lemon to go to"):
            archive.archive(conn, lemon.brief_of(conn, alone), 0.0)
        assert ledger.state(conn, task)["holder"] == f"brief:{alone}"


def test_a_running_parent_handed_an_archived_task_has_started_it(dead):
    lead, child = _registered("busy-lead"), _registered("child")
    with db.connect() as conn:
        db.add(conn, "claude:lead", "", metadata={})
        attached.attach(conn, "claude:lead", lemon.brief_of(conn, lead))
        conn.commit()
        links.set_parent(conn, child, lead)
        task = new_task(conn, brief_id=child, sponsor="")
        archive.archive(conn, lemon.brief_of(conn, child), 0.0)

        assert ledger.state(conn, task)["attached_at"] is not None
