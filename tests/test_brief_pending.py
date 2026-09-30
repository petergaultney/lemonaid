"""Who a waiting brief goes to: revived lemons, and windows named or renumbered by tmux."""

import argparse
import contextlib
import json
import shutil
import sqlite3
import subprocess
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


def test_a_running_codex_the_inbox_cannot_place_is_refused_with_candidates(
    capsys, tmux, monkeypatch
):
    """Its directory doesn't identify it: a Codex that exited there may still have a live row."""
    _brief("review")
    monkeypatch.setattr(selector, "_running_in", lambda session, index: [("codex", "/w")])
    with db.connect() as conn:
        db.add(conn, "codex:maybe-exited", "", metadata={"cwd": "/w"})
        db.add(conn, "codex:elsewhere", "", metadata={"cwd": "/other"})

    refused = _attach(capsys, "work:reviewer", "review")

    assert "pass --channel" in refused["error"]
    assert "codex:maybe-exited" in refused["error"]
    assert "codex:elsewhere" not in refused["error"]
    assert _attached_to("codex:maybe-exited") is None


def test_a_running_lemon_with_no_row_is_refused_rather_than_waited_for(capsys, tmux, monkeypatch):
    _brief("review")
    monkeypatch.setattr(selector, "_running_in", lambda session, index: [("claude", "/w")])

    refused = _attach(capsys, "work:reviewer", "review")

    assert "claude is already running" in refused["error"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_briefs").fetchone()[0] == 0
