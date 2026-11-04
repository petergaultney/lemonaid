import argparse
import contextlib
import json

from lemonaid.inbox import db
from lemonaid.tasks import cli
from lemonaid.tasks.inspection import task_input
from lemonaid.tasks.model import ledger

from .shared import new_task


def _run(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["task", "recheck", *argv, "--json"])
    with contextlib.suppress(SystemExit):
        args.func(args)

    return json.loads(capsys.readouterr().out)


def test_recheck_all_records_a_request_on_every_brief_held_task_for_the_checker(capsys):
    with db.connect() as conn:
        alpha = new_task(conn)
        bravo = new_task(conn, brief_id="Work.bravo", request_id="bravo")

    done = _run(capsys, "--all")

    with db.connect() as conn:
        state = ledger.state(conn, alpha)
        shown = task_input.fields(conn, state, {})
        assert ledger.consistent(conn, alpha)
    assert {r["task_id"] for r in done["requested"]} == {alpha, bravo}
    assert state["revision"] == 2
    assert shown["recheck.requested_at"] and shown["recheck.event"]


def test_naming_briefs_needs_one_or_all_and_reports_those_holding_nothing(capsys):
    with db.connect() as conn:
        made = new_task(conn)
        conn.executemany(
            "INSERT INTO lemon_identities (lemon_id, path) VALUES (?, ?)",
            [("Work.alpha", "/alpha.md"), ("Idle.one", "/idle.md")],
        )
        conn.commit()

    neither = _run(capsys)
    done = _run(capsys, "Work.alpha", "Idle.one")
    unknown = _run(capsys, "Nobody.here")

    assert "--all" in neither["error"]
    assert [r["task_id"] for r in done["requested"]] == [made]
    assert done["hold_no_task"] == ["Idle.one"]
    assert "Nobody.here" in unknown["error"]
