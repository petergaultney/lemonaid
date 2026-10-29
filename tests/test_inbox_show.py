"""`lemonaid inbox show` prints the inbox as `lma` draws it."""

import json
import sys
import time

import lemonaid.cli
from lemonaid import brief, groups
from lemonaid.inbox import db, headless_view
from lemonaid.stalls import inbox as stalls_inbox
from tests.inbox.tui.live.test_arrange_tui import _REVERSE, _configure, _serve, _sessions
from tests.stalls import test_inbox as test_stalls_inbox
from tests.stalls.shared import snap


def _show(monkeypatch, capsys, *args: str) -> str:
    monkeypatch.setattr(sys, "argv", ["lemonaid", "inbox", "show", *args])
    lemonaid.cli.main()
    return capsys.readouterr().out


def test_show_draws_the_arranged_rows_with_their_briefs_and_counts_the_fold(
    monkeypatch, tmp_path, capsys
):
    _, b, c = _sessions("a", "b", "c")
    path = tmp_path / "b.md"
    path.write_text("# Fix b\n\n## Now\n\n### Waiting on\n\n- CI on #12\n")
    with db.connect() as conn:
        brief.attached.attach(conn, "claude:b", path)
    _configure(_serve(tmp_path, _REVERSE))

    lines = _show(monkeypatch, capsys).splitlines()

    assert [line.split()[0] for line in lines if line[:6].strip().isdigit()] == [str(b), str(c)]
    assert any(line.strip() == "Waiting on: CI on #12" for line in lines)
    assert lines[-1] == "1 folded as 'quiet'; --folded lists them"


def test_show_json_lists_folded_rows_too(monkeypatch, tmp_path, capsys):
    a, b = _sessions("a", "b")
    _configure(_serve(tmp_path, _REVERSE))

    shown = json.loads(_show(monkeypatch, capsys, "--json"))

    assert [(r["id"], r["folded"], r["state"]) for r in shown["rows"]] == [
        (b, False, "idle"),
        (a, True, "idle"),
    ]
    assert (shown["fold_label"], shown["arrange_error"]) == ("quiet", "")


def test_show_keeps_the_members_a_group_hides_in_place(monkeypatch, tmp_path, capsys):
    a, b, c = _sessions("a", "b", "c")
    with db.connect() as conn:
        groups.store.add(conn, groups.store.create(conn, "g"), ["claude:a", "claude:b"])
        groups.store.add(conn, groups.store.create(conn, "shut"), ["claude:a", "claude:c"])
        conn.execute("UPDATE lemon_groups SET collapsed = 1 WHERE name = 'shut'")
        conn.commit()
    _configure(_serve(tmp_path, _REVERSE))

    shown = json.loads(_show(monkeypatch, capsys, "--json"))

    assert sorted((r["id"], r["folded"], r["group"]) for r in shown["rows"]) == [
        (a, True, "g, shut"),
        (b, False, "g"),
        (c, True, "shut"),
    ]


def test_show_stuck_fetches_the_prs_its_lemons_wait_on(monkeypatch, capsys):
    with db.connect() as conn:
        channel = test_stalls_inbox._lemon(conn, "widgets-238")
    monkeypatch.setattr(stalls_inbox, "fetch", lambda key: snap(decision="APPROVED"))
    later = time.time() + 3600
    monkeypatch.setattr(time, "time", lambda: later)

    rows = json.loads(_show(monkeypatch, capsys, "--json", "--stuck"))["rows"]

    assert [r["stuck"] for r in rows if r["channel"] == channel] == [
        "stuck 1h: Your move on #238; its brief should say `merge`"
    ]


def test_show_says_when_the_arranger_never_answers(monkeypatch, tmp_path, capsys):
    _sessions("a")
    _configure(_serve(tmp_path, "import time\ndef arrange(snapshot):\n    time.sleep(30)\n"))
    monkeypatch.setattr(headless_view, "_ARRANGE_WAIT", 0.3)

    shown = json.loads(_show(monkeypatch, capsys, "--json"))

    assert shown["arrange_error"] == "no answer in 0.3s"


def test_show_says_when_the_arranger_exits(monkeypatch, capsys):
    _sessions("a")
    _configure("sh -c 'exit 3'")
    monkeypatch.setattr(headless_view, "_ARRANGE_WAIT", 0.3)

    shown = json.loads(_show(monkeypatch, capsys, "--json"))

    assert shown["arrange_error"].startswith("exited 3")
