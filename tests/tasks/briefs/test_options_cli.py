"""`brief new` with `[tasks] enabled`: every new brief gets a task disposition."""

import argparse
import contextlib
import json
import re
import shlex
import sqlite3
from pathlib import Path

import pytest

import lemonaid.tasks.briefs.ensure_cli
import lemonaid.tasks.cli
from lemonaid.brief import identity, verbs_cli, write_cli
from lemonaid.inbox import db
from lemonaid.messages import store
from lemonaid.tasks.briefs import options_cli, planning
from lemonaid.tasks.model import associations, dependencies, holding, ledger, lifecycle, tree

from ..shared import new_task

_PARENT = "hq.BlessBar"


def _parsed(capsys, parser: argparse.ArgumentParser, argv: list[str]) -> dict:
    args = parser.parse_args(argv)
    with contextlib.suppress(SystemExit):
        args.func(args)

    return json.loads(capsys.readouterr().out)


def _run(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    write_cli.add_parsers(parser.add_subparsers())
    return _parsed(capsys, parser, ["new", "--child", "--parent", _PARENT, *argv, "--json"])


def _repair(capsys, error: str) -> dict:
    """Run the `brief task ensure` command a failed registration printed."""
    command = re.search(r"`lemonaid brief (task ensure [^`]*)`", error).group(1)
    parser = argparse.ArgumentParser()
    lemonaid.tasks.briefs.ensure_cli.add_parser(parser.add_subparsers())
    return _parsed(capsys, parser, [*shlex.split(command), "--json"])


def _as(monkeypatch, caller: str) -> None:
    monkeypatch.setattr(options_cli, "caller", lambda _conn: caller)


def _unwritable(*_args):
    raise OSError("read-only file system")


def _broken(*_args):
    raise sqlite3.OperationalError("disk I/O error")


@pytest.fixture
def review(tmp_path) -> tuple[str, ...]:
    pr = "https://github.com/acme/widgets/pull/12"
    doc = tmp_path / "vault" / "review.md"
    return ("--template", "review", "--pr", pr, "--output-doc", str(doc))


@pytest.fixture(autouse=True)
def _enabled(monkeypatch, tmp_path):
    for name in ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)
    vault = tmp_path / "vault"
    vault.mkdir()
    (tmp_path / "config.toml").write_text(
        f'[brief]\nvaults = ["{vault}"]\n\n[tasks]\nenabled = true\n'
    )
    path = tmp_path / "briefs" / "2026-09-01-hq.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"# hq\n\nLemon-ID: {_PARENT}\n")
    with db.connect() as conn:
        identity.ensure(conn, path)
    _as(monkeypatch, _PARENT)


def test_a_work_brief_gets_one_primary_task_and_ensure_does_not_duplicate_it(capsys):
    result = _run(capsys, "Fix the widget")
    again = _repair(capsys, f"`lemonaid brief task ensure {result['lemon_id']}`")

    with db.connect() as conn:
        task = ledger.state(conn, result["task_id"])
        count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        listed = [t["task_id"] for t in tree.rows(conn, _PARENT, False)]

    assert result["disposition"] == "new"
    assert (task["holder"], task["sponsor"], task["previous_holder"]) == (
        f"brief:{result['lemon_id']}",
        _PARENT,
        f"brief:{_PARENT}",
    )
    assert (task["description"], task["attached_at"]) == ("Fix the widget", None)
    assert (again["task_id"], again["created"], count) == (result["task_id"], False, 1)
    assert listed == [result["task_id"]]


def test_a_reviewer_takes_the_task_in_its_registration_and_an_observer_does_not(capsys, review):
    with db.connect() as conn:
        work = new_task(conn, brief_id=_PARENT, sponsor="")

    reviewer = _run(capsys, *review, "--task", f"task:{work}", "Review")
    observer = _run(capsys, "--task", work, "--observe", "Watch it")

    with db.connect() as conn:
        task = ledger.state(conn, work)
        assert (task["holder"], task["previous_holder"]) == (
            f"brief:{reviewer['lemon_id']}",
            f"brief:{_PARENT}",
        )
        assert associations.held_of(conn, reviewer["lemon_id"]) == [work]
        assert associations.held_of(conn, observer["lemon_id"]) == []
        assert [e["kind"] for e in ledger.history(conn, work)] == ["created", "assigned", "linked"]
    assert (reviewer["taken_from"], "notice" in reviewer) == ("", False)
    assert "ownership is NOT transferred" in observer["notice"]
    assert f"brief:{reviewer['lemon_id']}" in observer["notice"]


def test_the_review_template_makes_its_own_task_only_when_none_covers_the_pr(
    capsys, tmp_path, review
):
    refused = _run(capsys, *review, "Review it")
    teammates = _run(capsys, *review, "--new-task", "Review a teammate's PR")
    again = _run(capsys, *review, "--new-task", "Review ours")

    assert "--task TASK_ID" in refused["error"] and "--new-task" in refused["error"]
    assert teammates["disposition"] == "new"
    with db.connect() as conn:
        assert ledger.state(conn, teammates["task_id"])["subject_url"] == review[3]
    assert f"task:{teammates['task_id']}" in again["error"]
    assert not list((tmp_path / "briefs").glob("*-review-it.md"))
    assert not list((tmp_path / "briefs").glob("*-review-ours.md"))


def test_taking_a_task_from_another_holder_tells_it(capsys, monkeypatch, review):
    with db.connect() as conn:
        work = new_task(conn, brief_id="Other.lead", sponsor="")
    _as(monkeypatch, "Unrelated.lead")

    taken = _run(capsys, *review, "--task", work, "Take it over")

    with db.connect() as conn:
        assert ledger.state(conn, work)["holder"] == f"brief:{taken['lemon_id']}"
    assert taken["taken_from"] == "brief:Other.lead"
    assert "has been told" in taken["notice"]
    told = [p.read_text() for p in store.mailbox_for_id("Other.lead").glob("*.md")]
    assert len(told) == 1
    assert f"task:{work}" in told[0] and f"lemonaid tell {taken['lemon_id']}" in told[0]
    assert "From: Unrelated.lead" in told[0]


def test_a_transfer_planned_before_the_task_moved_is_refused():
    with db.connect() as conn:
        work = new_task(conn, brief_id=_PARENT, sponsor="")
        planned = planning.plan(conn, "task", work, "", _PARENT, _PARENT, "", False, False)
        with ledger.transaction(conn):
            holding.assign(conn, work, 1, "brief:Third.party", "", True, _PARENT, "move", 1.0)

        with pytest.raises(ledger.Refused, match="changed since it was planned"):
            options_cli.registration.register(conn, planned, "Late.reviewer", _PARENT, "x", 2.0)
        assert ledger.state(conn, work)["holder"] == "brief:Third.party"


@pytest.mark.parametrize(
    "options, check",
    [
        (["--no-task", "watches the area"], "exempt"),
        (["REVIEW", "--task", "WORK"], "task"),
        (["--for-task", "WORK"], "dependency"),
    ],
)
def test_repairing_a_failed_registration_records_the_intended_disposition(
    capsys, monkeypatch, review, options, check
):
    with db.connect() as conn:
        work = new_task(conn, brief_id=_PARENT, sponsor="")
    with monkeypatch.context() as patched:
        patched.setattr(options_cli.registration, "register", _broken)
        argv = [
            a for o in options for a in (review if o == "REVIEW" else [work if o == "WORK" else o])
        ]
        failed = _run(capsys, *argv, "Unlucky")

    assert Path(failed["path"]).is_file()
    repaired = _repair(capsys, failed["error"])
    again = _repair(capsys, failed["error"])

    with db.connect() as conn:
        match check:
            case "exempt":
                assert associations.exemption_of(conn, failed["lemon_id"]) == "watches the area"
            case "task":
                assert ledger.state(conn, work)["holder"] == f"brief:{failed['lemon_id']}"
            case "dependency":
                assert dependencies.waits_for(conn, work) == [repaired["task_id"]]
    assert repaired["created"] is True
    assert (again["created"], again["error"]) == (False, None)


def test_a_standing_role_records_its_exemption(capsys):
    result = _run(capsys, "--no-task", "watches the area", "Area watch")

    with db.connect() as conn:
        assert associations.exemption_of(conn, result["lemon_id"]) == "watches the area"
    assert result["disposition"] == "exempt"


def test_a_delegated_child_blocks_the_parents_only_task(capsys):
    with db.connect() as conn:
        mine = new_task(conn, brief_id=_PARENT, sponsor="")

    child = _run(capsys, "Part of it")

    with db.connect() as conn:
        assert dependencies.waits_for(conn, mine) == [child["task_id"]]
    assert child["parent_task_id"] == mine


def test_delegation_resolves_a_rerolled_parents_tasks(capsys):
    with db.connect() as conn:
        one = new_task(conn, brief_id="Old.lead", sponsor="")
        conn.execute(
            "INSERT INTO lemon_aliases (old_id, lemon_id) VALUES ('Old.lead', ?)", (_PARENT,)
        )
        conn.commit()

    child = _run(capsys, "After the reroll")
    with db.connect() as conn:
        new_task(conn, brief_id="Older.lead", sponsor="", request_id="two")
        conn.execute(
            "INSERT INTO lemon_aliases (old_id, lemon_id) VALUES ('Older.lead', ?)", (_PARENT,)
        )
        conn.commit()
    ambiguous = _run(capsys, "Now ambiguous")

    assert child["parent_task_id"] == one
    assert "--for-task" in ambiguous["error"]


def test_several_parent_tasks_need_a_choice_before_any_file_exists(capsys, tmp_path):
    with db.connect() as conn:
        first = new_task(conn, brief_id=_PARENT, sponsor="")
        second = new_task(conn, brief_id="Other.work", sponsor="")
        conn.execute("UPDATE tasks SET holder = ? WHERE task_id = ?", (f"brief:{_PARENT}", second))
        conn.commit()

    refused = _run(capsys, "Ambiguous")
    chosen = _run(capsys, "--for-task", second, "Chosen")
    alone = _run(capsys, "--independent", "Alone")

    assert "--for-task" in refused["error"]
    assert not list((tmp_path / "briefs").glob("*-ambiguous.md"))
    with db.connect() as conn:
        assert dependencies.waits_for(conn, second) == [chosen["task_id"]]
        assert dependencies.waits_for(conn, first) == []
    assert alone["parent_task_id"] == ""


def test_task_options_are_refused_while_tasks_are_off(capsys, tmp_path):
    (tmp_path / "config.toml").write_text("")

    assert "enabled" in _run(capsys, "--no-task", "x", "Off")["error"]
    assert "task_id" not in _run(capsys, "Plain")


def _attached(capsys, *argv: str) -> dict:
    with db.connect() as conn:
        db.add(conn, "claude:worker", "hello", metadata={})
    parser = argparse.ArgumentParser()
    write_cli.add_parsers(parser.add_subparsers())
    return _parsed(capsys, parser, ["new", "--channel", "claude:worker", *argv, "--json"])


def test_an_attached_brief_gets_a_task_with_its_clock_already_running(capsys):
    result = _attached(capsys, "Own work")

    with db.connect() as conn:
        task = ledger.state(conn, result["task_id"])
    assert result["disposition"] == "new"
    assert task["holder"] == f"brief:{result['lemon_id']}"
    assert task["attached_at"] is not None


def test_an_attached_brief_takes_the_same_task_options(capsys):
    assert _attached(capsys, "--no-task", "on call", "Pager")["disposition"] == "exempt"


def test_repairing_a_review_registration_keeps_the_pr_as_its_tasks_url(capsys, monkeypatch, review):
    with monkeypatch.context() as patched:
        patched.setattr(options_cli.registration, "register", _broken)
        failed = _run(capsys, *review, "--new-task", "Review a teammate's PR")

    repaired = _repair(capsys, failed["error"])

    with db.connect() as conn:
        assert ledger.state(conn, repaired["task_id"])["subject_url"] == review[3]


def test_repair_refuses_options_that_contradict_the_recorded_disposition(capsys):
    result = _run(capsys, "Work")

    refused = _repair(capsys, f"`lemonaid brief task ensure {result['lemon_id']} --no-task x`")

    assert "already holds task:" in refused["error"]


def test_a_brief_waiting_in_a_window_starts_no_clock(capsys, monkeypatch):
    def pending(_conn, _args, path):
        return {"path": str(path), "channel": None, "pending": "work:1"}, "", "pending"

    monkeypatch.setattr(write_cli, "_attach", pending)
    result = _attached(capsys, "Not started")

    with db.connect() as conn:
        assert ledger.state(conn, result["task_id"])["attached_at"] is None


def test_repairing_a_live_attached_brief_keeps_its_clock_running(capsys, monkeypatch):
    with monkeypatch.context() as patched:
        patched.setattr(options_cli.registration, "register", _broken)
        failed = _attached(capsys, "Live work")

    repaired = _repair(capsys, failed["error"])

    with db.connect() as conn:
        assert ledger.state(conn, repaired["task_id"])["attached_at"] is not None


def test_assigning_to_a_running_brief_starts_its_clock_and_tells_it(capsys):
    running = _attached(capsys, "--no-task", "on call", "Running reviewer")
    with db.connect() as conn:
        work = new_task(conn, brief_id=_PARENT, sponsor="")
    parser = argparse.ArgumentParser()
    lemonaid.tasks.cli.setup_parser(parser.add_subparsers())

    assigned = _parsed(
        capsys,
        parser,
        ["task", "assign", work, "--to", running["lemon_id"], "--reason", "ready", "--json"],
    )

    with db.connect() as conn:
        assert ledger.state(conn, work)["attached_at"] is not None
    told = [p.read_text() for p in store.mailbox_for_id(running["lemon_id"]).glob("*.md")]
    assert len(told) == 1 and f"lemonaid task assign {work}" in told[0]
    assert f"{running['lemon_id']} has been told" in assigned["notice"]


def test_a_failed_message_to_a_running_recipient_still_marks_the_assignment_as_messaged(
    capsys, monkeypatch
):
    running = _attached(capsys, "--no-task", "on call", "Unreachable reviewer")
    with db.connect() as conn:
        work = new_task(conn, brief_id=_PARENT, sponsor="")
    parser = argparse.ArgumentParser()
    lemonaid.tasks.cli.setup_parser(parser.add_subparsers())
    monkeypatch.setattr(store, "send", _unwritable)

    assigned = _parsed(
        capsys,
        parser,
        ["task", "assign", work, "--to", running["lemon_id"], "--reason", "ready", "--json"],
    )

    with db.connect() as conn:
        assert ledger.state(conn, work)["holder"] == f"brief:{running['lemon_id']}"
    assert "failed" in assigned["notice"]


def test_done_is_refused_while_the_brief_holds_an_open_task(capsys):
    child = _attached(capsys, "Finish me")
    parser = argparse.ArgumentParser()
    verbs_cli.add_parsers(parser.add_subparsers())

    def done() -> dict:
        return _parsed(capsys, parser, ["status", "--channel", "claude:worker", "done", "--json"])

    refused = done()
    with db.connect() as conn, ledger.transaction(conn):
        lifecycle.close(conn, child["task_id"], 1, "finished", "x", "close", 1.0)
    accepted = done()

    assert refused["open_tasks"] == [child["task_id"]]
    assert f"lemonaid task close {child['task_id']}" in refused["error"]
    assert accepted["error"] is None


def test_creating_a_task_for_a_running_brief_tells_it(capsys):
    running = _attached(capsys, "--no-task", "on call", "Busy one")
    parser = argparse.ArgumentParser()
    lemonaid.tasks.cli.setup_parser(parser.add_subparsers())
    argv = ["--brief", running["lemon_id"], "--assign", running["lemon_id"], "--description", "x"]

    created = _parsed(capsys, parser, ["task", "create", *argv, "--json"])

    with db.connect() as conn:
        state = ledger.state(conn, created["task_id"])
    assert state["attached_at"] is not None
    told = [p.read_text() for p in store.mailbox_for_id(running["lemon_id"]).glob("*.md")]
    assert len(told) == 1 and f"You now hold task:{created['task_id']}" in told[0]
