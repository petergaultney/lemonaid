import sqlite3
import subprocess
import time

from lemonaid.audit import actor, events
from lemonaid.inbox import self_session


def _no_ps(monkeypatch, parent=""):
    monkeypatch.setattr(actor, "_ps", lambda pid, field: parent if field == "comm" else "")


def _database(tmp_path, monkeypatch):
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as conn:
        conn.executescript(
            "CREATE TABLE session_briefs (channel TEXT, path TEXT);"
            "CREATE TABLE lemon_identities (path TEXT, lemon_id TEXT);"
            "INSERT INTO session_briefs VALUES ('claude:abc', '/b.md');"
            "INSERT INTO lemon_identities VALUES ('/b.md', 'Does a thing.WordyBin');"
        )
    monkeypatch.setattr(actor.db, "get_db_path", lambda: database)
    return database


def test_a_lemon_named_by_its_environment_is_its_brief_id_and_nothing_is_written(
    tmp_path, monkeypatch
):
    database = _database(tmp_path, monkeypatch)
    before = database.read_bytes()
    _no_ps(monkeypatch)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:abc")

    found = actor.caller()

    assert (found["who"], found["via"], found["channel"]) == (
        "Does a thing.WordyBin",
        "env",
        "claude:abc",
    )
    assert database.read_bytes() == before


def test_a_lemon_without_a_brief_is_its_channel(tmp_path, monkeypatch):
    _database(tmp_path, monkeypatch)
    _no_ps(monkeypatch)
    monkeypatch.setenv("CODEX_THREAD_ID", "t-1")

    assert actor.caller()["who"] == "codex:t-1"


def test_a_lemonaid_job_names_itself_before_the_environment_it_inherited(monkeypatch):
    _no_ps(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")
    monkeypatch.setenv(actor.ACTOR_ENV, "idle sweep")

    assert (actor.caller()["who"], actor.caller()["via"]) == ("idle sweep", "code")
    assert actor.caller("inbox watcher")["who"] == "inbox watcher"


def _in_a_lemons_pane(tmp_path, monkeypatch, ancestors):
    _database(tmp_path, monkeypatch)
    _no_ps(monkeypatch, "/bin/zsh")
    monkeypatch.setenv("TMUX_PANE", "%1")
    where = self_session.PaneLocation("/dev/ttys001", "work", "1")
    monkeypatch.setattr(actor.self_session, "pane_location", lambda pane: where)
    monkeypatch.setattr(actor.self_session, "resolve", lambda conn, at: ("claude:abc", ""))
    monkeypatch.setattr(
        actor.process,
        "ancestry",
        lambda pid: [actor.process.Identity(9, 1, "ttys001", "", name) for name in ancestors],
    )
    monkeypatch.setattr(actor.os, "isatty", lambda fd: True)
    monkeypatch.setattr(actor.getpass, "getuser", lambda: "sam")


def test_a_harness_child_in_a_lemons_pane_is_that_lemon(tmp_path, monkeypatch):
    _in_a_lemons_pane(tmp_path, monkeypatch, ["claude", "-zsh"])

    assert (actor.caller()["who"], actor.caller()["via"]) == ("Does a thing.WordyBin", "tmux")


def test_a_person_in_the_pane_of_a_suspended_lemon_is_the_person(tmp_path, monkeypatch):
    _in_a_lemons_pane(tmp_path, monkeypatch, ["zsh", "tmux"])

    assert (actor.caller()["who"], actor.caller()["via"]) == ("sam", "tty")


def test_a_person_at_a_terminal_is_their_login(monkeypatch):
    _no_ps(monkeypatch, "/bin/zsh")
    monkeypatch.setattr(actor.os, "isatty", lambda fd: True)
    monkeypatch.setattr(actor.getpass, "getuser", lambda: "sam")

    assert (actor.caller()["who"], actor.caller()["via"]) == ("sam", "tty")


def test_with_no_other_evidence_the_parent_process_then_unknown(monkeypatch):
    monkeypatch.setattr(actor.os, "isatty", lambda fd: False)
    _no_ps(monkeypatch, "/usr/sbin/cron")

    assert (actor.caller()["who"], actor.caller()["via"]) == ("cron", "ppid")

    _no_ps(monkeypatch)

    assert actor.caller()["who"] == "unknown"


def test_an_unreadable_database_still_names_the_harness_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(actor.db, "get_db_path", lambda: tmp_path / "missing" / "x.db")
    _no_ps(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abcdef0123456789")

    found = actor.caller()

    assert found["via"] == "env" and found["who"].startswith("claude:")


def test_the_lookup_gives_up_quickly_while_a_writer_holds_the_database(tmp_path, monkeypatch):
    database = tmp_path / "audit.db"
    writer = sqlite3.connect(database, isolation_level=None)
    writer.execute("CREATE TABLE session_briefs (channel TEXT, path TEXT)")
    writer.execute("BEGIN EXCLUSIVE")
    monkeypatch.setattr(actor.db, "get_db_path", lambda: database)
    _no_ps(monkeypatch)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:abc")

    started = time.monotonic()
    try:
        assert actor.caller()["who"] == "claude:abc"
    finally:
        writer.close()

    assert time.monotonic() - started < 2


def test_a_slow_ancestry_lookup_falls_back_and_the_event_is_kept(tmp_path, monkeypatch):
    _in_a_lemons_pane(tmp_path, monkeypatch, [])

    def slow(pid):
        raise subprocess.TimeoutExpired(["ps"], 3)

    monkeypatch.setattr(actor.process, "ancestry", slow)

    events.record("brief-edit", "Other.Lemon")

    [entry] = events.entries(0)
    assert (entry["who"], entry["via"]) == ("sam", "tty")
