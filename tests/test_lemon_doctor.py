"""`lemon doctor` reports facts about the lemons in scope, listing those that contradict their brief."""

import argparse
import json

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.lemon_facts import cli
from lemonaid.lineage import links
from lemonaid.messages import recipient, waiter
from lemonaid.watch import briefs_orphans


@pytest.fixture(autouse=True)
def _caller(monkeypatch):
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:lead")
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["-fish"])  # nothing runs there
    monkeypatch.setattr(briefs_orphans, "live_sessions", lambda socket: frozenset())
    _attach("lead", "claude:lead", "Status: working")


def _attach(name: str, channel: str, status: str, **metadata) -> str:
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\n{status}\n\n## Waiters\n\n- `lemonaid inbox watch --self`\n")
    with db.connect() as conn:
        db.add(
            conn, channel, "", metadata={"tty": f"/dev/{name}", **metadata}, switch_source="tmux"
        )
        attached.attach(conn, channel, path)
        return identity.ensure(conn, path)


def _child(name: str, channel: str, status: str) -> str:
    with db.connect() as conn:
        lead = identity.ensure(conn, brief_store.briefs_dir() / "lead.md")
    lemon_id = _attach(name, channel, status)
    with db.connect() as conn:
        links.set_parent(conn, lemon_id, lead)
    return lemon_id


def _doctor(*argv: str) -> int:
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["doctor", *argv])
    try:
        args.func(args)
    except SystemExit as exit:
        return int(exit.code or 0)

    return 0


def test_children_list_only_the_deaf_or_dead_ones_still_working(capsys):
    dead = _child("worker", "claude:worker", "Status: working")
    _child("finished", "claude:finished", "Status: done")

    assert _doctor("--children", "--self") == 1
    out = capsys.readouterr().out
    assert out.startswith("2 lemons, 1 deaf or dead")
    assert dead in out
    assert "finished" not in out
    assert "dead: its harness is not running" in out
    assert "waiters 0 running, 1 listed" in out


def test_json_gives_every_lemon_in_scope(capsys, monkeypatch):
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["claude"])
    monkeypatch.setattr(waiter, "is_armed", lambda inbox: True)
    _child("worker", "claude:worker", "Status: working")

    assert _doctor("--children", "--self", "--json") == 0
    (row,) = json.loads(capsys.readouterr().out)["lemons"]
    assert row["state"] == "listening"
    assert row["inbox_waiter"] is True
    assert row["waiters_listed"] == ["lemonaid inbox watch --self"]


def test_orphans_are_lemons_with_no_live_parent(capsys):
    orphan = _attach("stray", "claude:stray", "Status: blocked")
    child = _child("worker", "claude:worker", "Status: working")

    assert _doctor("--orphans", "--self", "--json") == 1
    ids = [row["lemon_id"] for row in json.loads(capsys.readouterr().out)["lemons"]]
    assert orphan in ids
    assert child in ids  # its parent, the lead, has no running tmux session here


def test_an_exit_is_reported_with_its_reason(capsys):
    lemon_id = _attach("quit", "claude:quit", "Status: working")
    with db.connect() as conn:
        db.record_exit(conn, "claude:quit", 1.0, "logout")

    _doctor(lemon_id)
    assert "(logout)" in capsys.readouterr().out


def test_a_lemon_asking_its_user_is_not_listed(capsys, monkeypatch):
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["claude"])
    _child("asking", "claude:asking", "Status: blocked")
    with db.connect() as conn:
        db.record_turn(conn, "claude:asking", 1.0)

    assert _doctor("--children", "--self") == 0
    assert capsys.readouterr().out == "1 lemons, 0 deaf or dead and not done or archived\n"


def test_an_unknown_name_is_skipped_and_the_rest_reported(capsys):
    lemon_id = _attach("worker", "claude:worker", "Status: working")

    _doctor("no-such-lemon", lemon_id, "--json")
    out = json.loads(capsys.readouterr().out)
    assert out["skipped"] == ["no-such-lemon"]
    assert [row["lemon_id"] for row in out["lemons"]] == [lemon_id]


def test_relative_scopes_need_self(capsys):
    assert _doctor("--children") == 2
    assert "add --self" in capsys.readouterr().err
