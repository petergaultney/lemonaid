import argparse
import contextlib
import json

from lemonaid.brief import attached
from lemonaid.inbox import db
from lemonaid.messages import store
from lemonaid.tasks import cli, cli_common
from lemonaid.tasks.model import holding, ledger

from .shared import idle, new_task, snapshot, task


def _run(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["task", *argv])
    with contextlib.suppress(SystemExit):
        args.func(args)

    return json.loads(capsys.readouterr().out)


def test_set_url_is_conditional_and_a_repeated_request_returns_its_result(capsys):
    with db.connect() as conn:
        made = new_task(conn)

    url = "https://example.com/pr/9"
    first = _run(capsys, "set-url", made, url, "--reason", "PR", "--request-id", "r1", "--json")
    again = _run(capsys, "set-url", made, url, "--reason", "PR", "--request-id", "r1", "--json")
    stale = _run(capsys, "set-url", made, "", "--reason", "x", "--expect-revision", "1", "--json")
    shown = _run(capsys, "show", f"task:{made}", "--json")

    assert first == again
    assert "expected revision 1" in stale["error"]
    assert (shown["subject_url"], shown["revision"]) == (url, 2)
    assert [e["kind"] for e in shown["events"]] == ["created", "url_set"]


def test_set_url_records_a_caller_whose_lemon_id_is_not_yet_recorded(capsys, monkeypatch, tmp_path):
    path = tmp_path / "briefs" / "caller.md"
    path.parent.mkdir()
    path.write_text("# Caller\n")
    with db.connect() as conn:
        made = new_task(conn)
        attached.attach(conn, "claude:caller", path)
        conn.commit()
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:caller")

    changed = _run(capsys, "set-url", made, "https://example.com/pr/9", "--reason", "PR", "--json")
    shown = _run(capsys, "show", f"task:{made}", "--json")

    assert changed["error"] is None
    assert shown["events"][-1]["actor"] not in ("", "cli")


def test_list_by_tree_and_export(capsys):
    with db.connect() as conn:
        made = new_task(conn)
        conn.execute(
            "INSERT INTO lemon_parents (lemon_id, parent_id, linked_at) VALUES ('Work.alpha', 'Lead.lead', 0)"
        )
        conn.commit()
        conn.execute("INSERT INTO lemon_identities (lemon_id, path) VALUES ('Lead.lead', '/x.md')")
        conn.commit()

    listed = _run(capsys, "list", "--tree", "Lead.lead", "--json")
    exported = _run(capsys, "export")

    assert [t["task_id"] for t in listed["tasks"]] == [made]
    assert [t["task_id"] for t in exported["tasks"]] == [made]


def test_replay_exits_nonzero_listing_unexpected_verdicts(capsys, tmp_path):
    path = tmp_path / "corpus.json"
    path.write_text(
        json.dumps({"snapshots": [snapshot([task()], idle(), expected={"t1": "wait"})]})
    )

    result = _run(capsys, "replay", str(path), "--json")

    assert [(c["task_id"], c["verdict"]) for c in result["changed"]] == [("t1", "challenge")]


def _known(conn, *lemon_ids: str) -> None:
    for lemon_id in lemon_ids:
        conn.execute(
            "INSERT INTO lemon_identities (lemon_id, path) VALUES (?, ?)",
            (lemon_id, f"/{lemon_id}.md"),
        )
    conn.commit()


def test_assign_by_the_holder_tells_nobody_and_by_anyone_else_tells_the_holder(capsys, monkeypatch):
    with db.connect() as conn:
        made = new_task(conn)
        _known(conn, "Review.one", "Lead.lead")
    monkeypatch.setattr(cli_common, "actor", lambda _conn: "Work.alpha")
    pushed = _run(capsys, "assign", made, "--to", "Review.one", "--reason", "ready", "--json")
    monkeypatch.setattr(cli_common, "actor", lambda _conn: "Lead.lead")
    taken = _run(capsys, "assign", made, "--to", "Lead.lead", "--reason", "taking over", "--json")

    assert (pushed["holder"], pushed["taken_from"], pushed["notice"]) == (
        "brief:Review.one",
        "",
        "",
    )
    assert (taken["holder"], taken["taken_from"]) == ("brief:Lead.lead", "brief:Review.one")
    told = [p.read_text() for p in store.inbox_for_id("Review.one").glob("*.md")]
    assert len(told) == 1 and "was taken from you" in told[0]
    assert not store.inbox_for_id("Work.alpha").exists()
    with db.connect() as conn:
        assert ledger.consistent(conn, made)


def test_an_external_holder_needs_a_recheck_and_a_human_one_is_answered_for(capsys):
    with db.connect() as conn:
        made = new_task(conn)
        _known(conn, "Work.alpha")
        with ledger.transaction(conn):
            holding.assign(
                conn,
                made,
                1,
                "human:sam",
                "decide",
                False,
                "Work.alpha",
                "h",
                1.0,
                accountable="Lead.lead",
            )

    no_recheck = _run(
        capsys,
        "assign",
        made,
        "--to",
        "external:ci",
        "--reason",
        "x",
        "--accountable",
        "Work.alpha",
        "--json",
    )
    back = _run(capsys, "assign", made, "--to", "Work.alpha", "--reason", "decided", "--json")

    assert "recheck" in no_recheck["error"]
    assert back["taken_from"] == "human:sam"
    told = [p.read_text() for p in store.inbox_for_id("Lead.lead").glob("*.md")]
    assert len(told) == 1 and "taken from human:sam, which you answer for" in told[0]


def test_a_repeated_assign_request_sends_no_message_again(capsys, monkeypatch):
    with db.connect() as conn:
        made = new_task(conn)
        _known(conn, "New.owner", "Work.alpha")
    monkeypatch.setattr(cli_common, "actor", lambda _conn: "New.owner")
    take = ("assign", made, "--to", "New.owner", "--reason", "take", "--request-id", "once")

    first = _run(capsys, *take, "--json")
    again = _run(capsys, *take, "--json")
    _run(capsys, "assign", made, "--to", "Work.alpha", "--reason", "give back", "--json")
    later = _run(capsys, *take, "--json")

    assert (first["taken_from"], again["notice"], later["notice"]) == ("brief:Work.alpha", "", "")
    assert len(list(store.inbox_for_id("Work.alpha").glob("*.md"))) == 1
