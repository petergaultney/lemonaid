"""Briefs attached to lemon sessions: what `show` finds, and who a waiting brief goes to."""

import argparse
import contextlib
import json
from pathlib import Path

import pytest

from lemonaid.brief import attached, session, status, store, target, write_cli
from lemonaid.inbox import db, self_session


@pytest.fixture(autouse=True)
def _fake_tmux(monkeypatch, tmp_path):
    monkeypatch.setattr(session, "session_dir", lambda s: tmp_path / "place")
    monkeypatch.setattr(session, "lemon_name", lambda s: "")


def _lemon(channel: str, tmux_session: str, window: str, created_at: float) -> db.Notification:
    with db.connect() as conn:
        return db.add(
            conn,
            channel,
            "",
            metadata={"tmux_session": tmux_session, "tmux_window": window},
            created_at=created_at,
        )


def _brief(name: str) -> Path:
    path = store.briefs_dir() / f"{name}.md"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n\nStatus: working\n\n## Now\n- Starting.\n")
    return path.resolve()


def _run(capsys, *argv: str) -> dict | list:
    parser = argparse.ArgumentParser()
    write_cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args([*argv, "--json"])
    with contextlib.suppress(SystemExit):
        args.func(args)

    return json.loads(capsys.readouterr().out)


def _attached_to(channel: str) -> Path | None:
    with db.connect() as conn:
        attached.claim_pending(conn)
        return attached.by_channel(conn, [channel]).get(channel)


def test_a_session_holding_two_lemons_needs_a_window(capsys):
    _lemon("claude:author", "work", "2", 1)
    _lemon("codex:reviewer", "work", "4", 2)
    _brief("review")

    refused = _run(capsys, "attach", "--session", "work", "review")
    chosen = _run(capsys, "attach", "--session", "work:4", "review")

    assert "work:2, work:4" in refused["error"]
    assert chosen["channel"] == "codex:reviewer"
    assert _attached_to("codex:reviewer") == _brief("review")


def test_attaching_a_brief_elsewhere_moves_it(capsys):
    _lemon("claude:a", "one", "2", 1)
    _lemon("claude:b", "two", "2", 1)
    _brief("task")

    _run(capsys, "attach", "--channel", "claude:a", "task")
    moved = _run(capsys, "attach", "--channel", "claude:b", "task")

    assert moved["moved_from"] == "claude:a"
    assert _attached_to("claude:a") is None


def test_a_waiting_brief_goes_to_the_first_lemon_started_after_it():
    _lemon("claude:old", "fresh", "2", 100)
    with db.connect() as conn:
        attached.attach_pending(conn, "fresh", "2", _brief("task"), attached.newest_id(conn))
    _lemon("claude:elsewhere", "fresh", "3", 300)
    _lemon("claude:new", "fresh", "2", 400)
    _lemon("claude:newer", "fresh", "2", 500)

    assert _attached_to("claude:new") == _brief("task")
    assert _attached_to("claude:old") is None
    assert _attached_to("claude:elsewhere") is None
    assert _attached_to("claude:newer") is None


def test_a_running_lemon_that_speaks_again_is_not_new():
    _lemon("codex:running", "fresh", "2", 100)
    with db.connect() as conn:
        attached.attach_pending(conn, "fresh", "2", _brief("task"), attached.newest_id(conn))
    _lemon("codex:running", "fresh", "2", 10**10)  # a notification refreshes created_at

    assert _attached_to("codex:running") is None

    _lemon("codex:started", "fresh", "2", 10**10 + 1)

    assert _attached_to("codex:started") == _brief("task")


def test_a_brief_outside_the_briefs_folder_is_refused(capsys, tmp_path):
    _lemon("claude:a", "work", "2", 1)
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_text("# x\n\nStatus: working\n")

    absolute = _run(capsys, "attach", "--channel", "claude:a", str(elsewhere))
    escaping = _run(capsys, "attach", "--channel", "claude:a", "../elsewhere")

    assert "not inside" in absolute["error"]
    assert "not inside" in escaping["error"]
    assert _attached_to("claude:a") is None


def test_now_refuses_an_attachment_outside_the_briefs_folder(capsys, tmp_path):
    _lemon("claude:a", "work", "2", 1)
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_text("# x\n\nStatus: working\n")
    with db.connect() as conn:
        attached.attach(conn, "claude:a", elsewhere)

    refused = _run(capsys, "status", "--channel", "claude:a", "done")

    assert "not inside" in refused["error"]
    assert "Status: working" in elsewhere.read_text()


def test_a_symlink_out_of_the_briefs_folder_is_refused(capsys, tmp_path):
    _lemon("claude:a", "work", "2", 1)
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_text("# x\n\nStatus: working\n")
    store.briefs_dir().mkdir(parents=True, exist_ok=True)
    (store.briefs_dir() / "sneaky.md").symlink_to(elsewhere)

    assert "not inside" in _run(capsys, "attach", "--channel", "claude:a", "sneaky")["error"]


def test_attaching_to_an_empty_window_waits_for_its_lemon(capsys):
    _brief("task")

    waiting = _run(capsys, "attach", "--session", "fresh:2", "task")
    [listed] = _run(capsys, "list")
    _lemon("claude:new", "fresh", "2", 10**10)

    assert waiting["pending"] == "fresh:2"
    assert listed["pending"] is True
    assert _attached_to("claude:new") == _brief("task")


def test_list_maps_a_brief_file_back_to_its_session(capsys):
    row = _lemon("claude:a", "work", "2", 1)
    _run(capsys, "attach", "--channel", "claude:a", str(_brief("task")))

    [entry] = _run(capsys, "list")

    assert entry["path"] == str(_brief("task"))
    assert (entry["channel"], entry["id"], entry["tmux_session"], entry["tmux_window"]) == (
        "claude:a",
        row.id,
        "work",
        "2",
    )


def test_now_and_status_edit_the_attached_brief(capsys):
    _lemon("codex:t1", "work", "4", 1)
    _run(capsys, "attach", "--channel", "codex:t1", str(_brief("task")))

    _run(capsys, "now", "--channel", "codex:t1", "- Done: the parser.")
    _run(capsys, "status", "--channel", "codex:t1", "done", "PR #9")

    text = _brief("task").read_text()
    assert "Status: done - PR #9" in text
    assert "## Now\n- Done: the parser.\n" in text


def test_now_without_an_attached_brief_says_how_to_get_one(capsys):
    _lemon("claude:a", "work", "2", 1)

    assert "brief attach" in _run(capsys, "now", "--channel", "claude:a", "x")["error"]


def test_new_creates_and_attaches(capsys):
    _lemon("claude:a", "work", "2", 1)

    made = _run(capsys, "new", "--channel", "claude:a", "Fix the thing")

    assert Path(made["path"]).name.endswith("-fix-the-thing.md")
    assert _attached_to("claude:a") == Path(made["path"])


def test_an_attached_brief_wins_over_the_places_notes(tmp_path):
    notes = tmp_path / "place" / ".z"
    notes.mkdir(parents=True)
    (notes / "brief.md").write_text("# the place's\n\nStatus: working\n")
    row = _lemon("claude:a", "work", "2", 1)
    found = target.for_notification(row, {"claude:a": _brief("mine")})

    out = status.render(found.attached, found.dirs, found.place, found.names, now=1)

    assert out.startswith("## mine")
    assert "the place's" not in out


def test_the_window_picks_one_lemons_brief_from_a_shared_session():
    rows = [_lemon("claude:author", "work", "2", 1), _lemon("codex:reviewer", "work", "4", 2)]
    briefs = {"claude:author": _brief("author"), "codex:reviewer": _brief("review")}

    assert target.for_session("work", rows, briefs, "4").attached == [_brief("review")]
    assert target.for_session("work", rows, briefs, "1").attached == [
        _brief("review"),
        _brief("author"),
    ]


def test_a_missing_attached_brief_says_so(tmp_path):
    out = status.render([tmp_path / "gone.md"], [], None, [], now=1)

    assert "does not exist" in out


def test_self_is_the_one_lemon_recorded_at_the_calling_pane(capsys, monkeypatch):
    here = self_session.PaneLocation("/dev/ttys7", "work", "4")
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(self_session, "pane_location", lambda pane: here)
    with db.connect() as conn:
        db.add(
            conn,
            "claude:author",
            "",
            metadata={"tty": "/dev/ttys2", "tmux_session": "work", "tmux_window": "2"},
        )
        db.add(
            conn,
            "codex:reviewer",
            "",
            metadata={"tty": "/dev/ttys7", "tmux_session": "work", "tmux_window": "4"},
        )

    attached_self = _run(capsys, "attach", "--self", str(_brief("review")))

    assert attached_self["channel"] == "codex:reviewer"


def test_self_refuses_to_guess_between_two_lemons_at_one_pane(capsys, monkeypatch):
    here = self_session.PaneLocation("/dev/ttys7", "work", "4")
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(self_session, "pane_location", lambda pane: here)
    with db.connect() as conn:
        for channel in ("codex:one", "codex:two"):
            db.add(
                conn,
                channel,
                "",
                metadata={"tty": "/dev/ttys7", "tmux_session": "work", "tmux_window": "4"},
            )

    refused = _run(capsys, "attach", "--self", str(_brief("review")))

    assert "--channel" in refused["error"]
