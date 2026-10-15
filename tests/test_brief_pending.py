"""Who a waiting brief goes to: revived lemons, and windows named or renumbered by tmux."""

import argparse
import contextlib
import json
import shutil
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from lemonaid.brief import attached, selector, store, write_cli
from lemonaid.inbox import db
from lemonaid.inbox.migrations import m011_pending_briefs_live_before


def _lemon(channel: str, tmux_session: str, window: str) -> db.Notification:
    with db.connect() as conn:
        return db.add(
            conn, channel, "", metadata={"tmux_session": tmux_session, "tmux_window": window}
        )


def _brief(name: str) -> Path:
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: working\n")
    return path.resolve()


def _attached_to(channel: str) -> Path | None:
    with db.connect() as conn:
        attached.claim_pending(conn)
        return attached.by_channel(conn, [channel]).get(channel)


def _attach(capsys, spec: str, brief: str) -> dict:
    parser = argparse.ArgumentParser()
    write_cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args(["attach", "--session", spec, "--json", brief])
    with contextlib.suppress(SystemExit):
        args.func(args)
    return json.loads(capsys.readouterr().out)


@pytest.fixture
def tmux(monkeypatch):
    """A private tmux server with session `work`: window `main`, then window `reviewer`."""
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-test-{uuid.uuid4().hex[:8]}"

    def run(*args: str) -> str:
        return subprocess.run(
            ["tmux", "-L", name, *args], capture_output=True, text=True
        ).stdout.strip()

    subprocess.run(
        ["tmux", "-L", name, "-f", "/dev/null", "new-session", "-d", "-s", "work", "-n", "main"],
        check=True,
    )
    run("new-window", "-d", "-t", "work", "-n", "reviewer")
    monkeypatch.setenv("TMUX", f"{run('display', '-p', '#{socket_path}')},0,0")
    try:
        yield run
    finally:
        run("kill-server")


def test_a_lemon_revived_from_the_archive_into_the_window_gets_the_brief():
    old = _lemon("claude:resumed", "fresh", "2")
    with db.connect() as conn:
        db.archive(conn, old.id)
        attached.attach_pending(conn, "fresh", "2", _brief("task"), attached.live_channels(conn))
        db.register_working(
            conn,
            "claude:resumed",
            "",
            metadata={"tmux_session": "fresh", "tmux_window": "2"},
        )

    assert _attached_to("claude:resumed") == _brief("task")


def test_an_archived_lemon_left_in_the_window_does_not_get_the_brief():
    old = _lemon("claude:gone", "fresh", "2")
    with db.connect() as conn:
        db.archive(conn, old.id)
        attached.attach_pending(conn, "fresh", "2", _brief("task"), attached.live_channels(conn))

    assert _attached_to("claude:gone") is None

    _lemon("claude:new", "fresh", "2")

    assert _attached_to("claude:new") == _brief("task")
    assert _attached_to("claude:gone") is None


def test_a_window_named_by_tmux_is_the_window_its_lemon_records(capsys, tmux):
    _brief("review")
    index = tmux("display", "-p", "-t", "=work:reviewer", "#{window_index}")

    waiting = _attach(capsys, "work:reviewer", "review")
    _lemon("codex:reviewer", "work", index)

    assert waiting["pending"] == f"work:{index}"
    assert _attached_to("codex:reviewer") == _brief("review")


def test_a_window_name_tmux_does_not_know_is_refused(capsys, tmux):
    _brief("review")

    refused = _attach(capsys, "work:nobody", "review")

    assert "No window 'nobody'" in refused["error"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_briefs").fetchone()[0] == 0


def test_a_waiting_window_is_followed_when_tmux_renumbers_it(capsys, tmux):
    _brief("review")
    before = tmux("display", "-p", "-t", "=work:reviewer", "#{window_index}")
    _attach(capsys, "work:reviewer", "review")

    tmux("move-window", "-s", "=work:reviewer", "-t", "work:9")
    _lemon("codex:at-old-index", "work", before)
    _lemon("codex:reviewer", "work", "9")

    assert _attached_to("codex:at-old-index") is None
    assert _attached_to("codex:reviewer") == _brief("review")


def test_a_brief_waiting_from_before_the_upgrade_keeps_waiting(tmp_path):
    path = tmp_path / "upgrade.db"
    with db.connect(path):
        pass
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE pending_briefs")
    conn.execute(
        "CREATE TABLE pending_briefs (tmux_session TEXT NOT NULL, tmux_window TEXT NOT NULL,"
        " path TEXT NOT NULL, after_id INTEGER NOT NULL, requested_at REAL NOT NULL,"
        " PRIMARY KEY (tmux_session, tmux_window))"
    )
    for channel, status in (("claude:running", "read"), ("claude:gone", "archived")):
        conn.execute(
            "INSERT INTO notifications (channel, message, metadata, created_at, status)"
            " VALUES (?, '', ?, 1, ?)",
            (channel, json.dumps({"tmux_session": "fresh", "tmux_window": "2"}), status),
        )
    conn.execute("INSERT INTO pending_briefs VALUES ('fresh', '2', '/b/task.md', 2, 1)")
    conn.execute(f"PRAGMA user_version = {m011_pending_briefs_live_before.VERSION - 1}")
    conn.commit()
    conn.close()
    db._initialized_dbs.discard(path)

    with db.connect(path) as conn:
        [row] = conn.execute("SELECT * FROM pending_briefs").fetchall()
        attached.claim_pending(conn)

        assert json.loads(row["live_before"]) == ["claude:running"]
        assert row["tmux_window_id"] == ""
        assert attached.by_channel(conn, ["claude:running", "claude:gone"]) == {}


def test_a_waiting_name_is_given_to_the_lemon_that_claims_the_brief():
    with db.connect() as conn:
        attached.attach_pending(conn, "fresh", "4", _brief("task"), [], name="REVIEW #9")
    _lemon("codex:reviewer", "fresh", "4")

    assert _attached_to("codex:reviewer") == _brief("task")
    with db.connect() as conn:
        assert db.get_by_channel(conn, "codex:reviewer", unread_only=False).name == "REVIEW #9"


def test_a_codex_on_the_shared_daemon_is_refused_with_candidates(capsys, tmux, monkeypatch):
    """Its row is never placed, and its directory doesn't identify it."""
    _brief("review")
    monkeypatch.setattr(selector, "_running_in", lambda session, index: [("codex", "/w", True)])
    with db.connect() as conn:
        db.add(conn, "codex:maybe-exited", "", metadata={"cwd": "/w"})
        db.add(conn, "codex:elsewhere", "", metadata={"cwd": "/other"})

    refused = _attach(capsys, "work:reviewer", "review")

    assert "shared app-server" in refused["error"]
    assert "codex:maybe-exited" in refused["error"]
    assert "codex:elsewhere" not in refused["error"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_briefs").fetchone()[0] == 0


def test_a_running_codex_not_yet_placed_claims_the_brief_once_it_is(capsys, tmux, monkeypatch):
    """Its row already exists when the brief starts waiting, so it isn't counted as live before."""
    _brief("review")
    index = tmux("display", "-p", "-t", "=work:reviewer", "#{window_index}")
    monkeypatch.setattr(selector, "_running_in", lambda session, index: [("codex", "/w", False)])
    with db.connect() as conn:
        db.add(conn, "codex:starting", "", metadata={"cwd": "/w", "tty": "/dev/ttys9"})

    waiting = _attach(capsys, "work:reviewer", "review")
    assert waiting["pending"] == f"work:{index}"
    assert _attached_to("codex:starting") is None

    with db.connect() as conn:
        db.record_location(conn, "codex:starting", "work", index)

    assert _attached_to("codex:starting") == _brief("review")


def test_a_placed_lemon_live_before_the_brief_waited_does_not_claim_it():
    _lemon("claude:already-there", "fresh", "4")
    with db.connect() as conn:
        attached.attach_pending(conn, "fresh", "4", _brief("task"), attached.live_channels(conn))

    assert _attached_to("claude:already-there") is None


def test_a_waiting_brief_attached_by_channel_since_stops_waiting():
    with db.connect() as conn:
        attached.attach_pending(conn, "fresh", "4", _brief("task"), [])
        conn.execute("UPDATE pending_briefs SET requested_at = requested_at - 60")
        conn.commit()
    _lemon("codex:by-channel", "elsewhere", "2")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO session_briefs (channel, path, attached_at) VALUES (?, ?, ?)",
            ("codex:by-channel", str(_brief("task")), time.time()),
        )
        conn.commit()
        attached.claim_pending(conn)

        assert conn.execute("SELECT COUNT(*) FROM pending_briefs").fetchone()[0] == 0


def test_a_brief_moved_to_a_new_window_keeps_waiting():
    """Attached before it was set waiting, so the new window's lemon still gets it."""
    _lemon("claude:old", "fresh", "2")
    with db.connect() as conn:
        attached.attach(conn, "claude:old", _brief("task"))
        attached.attach_pending(conn, "fresh", "4", _brief("task"), attached.live_channels(conn))
    _lemon("codex:new", "fresh", "4")

    assert _attached_to("codex:new") == _brief("task")


def test_a_window_already_running_two_lemons_is_refused(capsys, tmux, monkeypatch):
    """Whichever is placed first would get the brief, which may be meant for the other."""
    _brief("review")
    monkeypatch.setattr(
        selector,
        "_running_in",
        lambda session, index: [("claude", "/w", False), ("codex", "/w", False)],
    )

    refused = _attach(capsys, "work:reviewer", "review")

    assert "could go to either" in refused["error"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_briefs").fetchone()[0] == 0


def _ps(monkeypatch, out: str) -> None:
    monkeypatch.setattr(
        selector.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, out, ""),
    )


def test_only_the_codex_process_arguments_say_it_is_local(monkeypatch):
    _ps(monkeypatch, "xonsh -c 'echo --no-daemon'\nnode /bin/codex\n/vendor/bin/codex\n")

    assert selector._codex_on_daemon("/dev/ttys1")


def test_a_codex_started_with_no_daemon_is_local(monkeypatch):
    _ps(monkeypatch, "xonsh -c codex --no-daemon\n/vendor/bin/codex --no-daemon go\n")

    assert not selector._codex_on_daemon("/dev/ttys1")


def test_a_tty_with_no_codex_process_counts_as_on_the_daemon(monkeypatch):
    _ps(monkeypatch, "xonsh\n")

    assert selector._codex_on_daemon("/dev/ttys1")
