import argparse
import contextlib
import json
import shlex

from lemonaid import brief
from lemonaid.brief import attached
from lemonaid.inbox import db
from lemonaid.messages import store
from lemonaid.tasks import cli, cli_common
from lemonaid.tasks.model import dependencies, ledger, lifecycle

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


def test_assign_tells_the_new_holder_and_a_holder_its_task_was_taken_from(
    capsys, monkeypatch, dead
):
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
        "Review.one has been told",
    )
    assert (taken["holder"], taken["taken_from"]) == ("brief:Lead.lead", "brief:Review.one")
    told = sorted(p.read_text() for p in store.mailbox_for_id("Review.one").glob("*.md"))
    assert len(told) == 2 and any("was taken from you" in m for m in told)
    assert not store.mailbox_for_id("Work.alpha").exists()
    with db.connect() as conn:
        assert ledger.consistent(conn, made)


def test_assign_takes_only_a_live_lemon(capsys, dead):
    with db.connect() as conn:
        made = new_task(conn)
        _known(conn, "Gone.one")
    dead.add("Gone.one")

    person = _run(capsys, "assign", made, "--to", "human:sam", "--reason", "x", "--json")
    gone = _run(capsys, "assign", made, "--to", "Gone.one", "--reason", "x", "--json")

    assert person["error"] and gone["error"]
    assert "lemonaid lemon resume Gone.one" in gone["error"]
    with db.connect() as conn:
        assert ledger.state(conn, made)["holder"] == "brief:Work.alpha"


def test_a_retried_assignment_returns_its_result_after_the_receiver_dies(capsys, dead):
    with db.connect() as conn:
        made = new_task(conn)
        _known(conn, "Review.one")
    take = ("assign", made, "--to", "Review.one", "--reason", "x", "--request-id", "r", "--json")

    first = _run(capsys, *take)
    dead.add("Review.one")
    again = _run(capsys, *take)

    assert first["error"] is None and again == {**first, "notice": ""}


def test_create_refuses_a_holder_that_isnt_live(capsys, dead):
    with db.connect() as conn:
        _known(conn, "Gone.one")
    dead.add("Gone.one")

    made = _run(
        capsys,
        "create",
        "--brief",
        "Gone.one",
        "--assign",
        "Gone.one",
        "--description",
        "x",
        "--json",
    )

    assert "lemonaid lemon resume Gone.one" in made["error"]


def test_a_closed_task_a_person_held_still_lists_and_shows(capsys):
    with db.connect() as conn:
        made = new_task(conn)
        _known(conn, "Work.alpha")
        with ledger.transaction(conn):
            ledger.append(
                conn,
                made,
                1,
                "assigned",
                {"holder": "human:Ben", "reason": "x"},
                "Work.alpha",
                "h",
                2.0,
            )
            ledger.append(conn, made, 2, "closed", {"reason": "merged"}, "Work.alpha", "c", 3.0)

    listed = _run(capsys, "list", "--tree", "Work.alpha", "--include-closed", "--json")
    shown = _run(capsys, "show", made, "--json")

    assert [t["holder"] for t in listed["tasks"] if t["task_id"] == made] == ["human:Ben"]
    assert (shown["holder"], shown["lifecycle"]) == ("human:Ben", "closed")


def test_a_repeated_assign_request_sends_no_message_again(capsys, monkeypatch, dead):
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
    assert len(list(store.mailbox_for_id("Work.alpha").glob("*.md"))) == 2  # taken, then given back


def test_depend_waits_only_for_another_open_task_and_refuses_a_cycle(capsys):
    with db.connect() as conn:
        mine = new_task(conn)
        theirs = new_task(conn, brief_id="Other.one", request_id="theirs")

        done = new_task(conn, brief_id="Done.one", request_id="done")
        with ledger.transaction(conn):
            lifecycle.close(conn, done, 1, "finished", "Done.one", "close", 200.0)

    waits = _run(capsys, "depend", mine, "--on", f"task:{theirs}", "--json")
    cycle = _run(capsys, "depend", theirs, "--on", mine, "--json")
    missing = _run(capsys, "depend", mine, "--on", "00000000-0000-0000-0000-000000000000", "--json")
    closed = _run(capsys, "depend", mine, "--on", done, "--json")

    assert waits["error"] is None and waits["on"] == theirs
    assert "cycle" in cycle["error"]
    assert "isn't an open task" in missing["error"] and "isn't an open task" in closed["error"]
    with db.connect() as conn:
        assert dependencies.waits_for(conn, mine) == [theirs]


def test_set_url_takes_a_file_path_and_hints_when_the_holders_brief_doesnt_watch_it(
    capsys, tmp_path
):
    path = brief.store.briefs_dir() / "work.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Work\n\nBrief-ID: Work.alpha\n\n## Goal\n")
    doc = (tmp_path / "My Design.md").resolve()
    with db.connect() as conn:
        made = new_task(conn)
        conn.execute(
            "INSERT INTO lemon_identities (lemon_id, path) VALUES ('Work.alpha', ?)", (str(path),)
        )
        conn.commit()

    changed = _run(capsys, "set-url", made, str(doc), "--reason", "its doc", "--json")
    shown = _run(capsys, "show", f"task:{made}", "--json")

    assert shown["subject_url"] == doc.as_uri()
    suggested = shlex.split(changed["notice"].split("`")[1])

    assert suggested == ["lemonaid", "brief", "doc", "add", "--self", str(doc), "PURPOSE"]
