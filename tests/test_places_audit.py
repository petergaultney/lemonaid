import argparse
import json
import sqlite3
import time

from lemonaid.places import audit, log_cli


def _record(action="toss", outcome="tearing-down", key="feat", **kw):
    audit.record(action, outcome, key=key, session=kw.pop("session", "feat"), **kw)


def test_record_appends_a_json_line_with_the_caller(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(audit, "_lemon_id", lambda: "Some thing.SwearDig")

    _record(flags=["--yes"], reason="why", directory="/d")

    [line] = (tmp_path / "logs" / "places.log").read_text().splitlines()
    entry = json.loads(line)
    assert entry | {"at": "", "pid": 0, "parent": "", "tty": ""} == {
        "at": "",
        "action": "toss",
        "outcome": "tearing-down",
        "key": "feat",
        "dir": "/d",
        "session": "feat",
        "flags": ["--yes"],
        "reason": "why",
        "who": "Some thing.SwearDig",
        "pid": 0,
        "parent": "",
        "tty": "",
    }
    assert entry["at"][-6] in "+-" and entry["pid"] > 0


def test_unidentified_caller_falls_back_to_parent_process_then_unknown(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(audit, "_lemon_id", lambda: "")
    monkeypatch.setattr(audit, "_ps", lambda pid, field: "/bin/zsh" if field == "comm" else "")

    assert audit.caller()["who"] == "zsh"

    monkeypatch.setattr(audit, "_ps", lambda pid, field: "")

    assert audit.caller()["who"] == "unknown"


def test_log_rotates_past_the_size_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(audit, "_lemon_id", lambda: "")
    monkeypatch.setattr(audit, "_MAX_BYTES", 10)

    _record(key="old")
    _record(key="new")

    assert [e["key"] for e in audit.entries(0)] == ["old", "new"]
    assert (tmp_path / "logs" / "places.log.1").exists()
    assert len((tmp_path / "logs" / "places.log").read_text().splitlines()) == 1


def test_entries_filter_by_key_or_session_and_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(audit, "_lemon_id", lambda: "")
    _record(key="a", session="s1")
    _record(key="b", session="s2")
    _record(key="a", session="s1", outcome="declined")

    assert [e["outcome"] for e in audit.entries(10, "a")] == ["tearing-down", "declined"]
    assert [e["key"] for e in audit.entries(10, "s2")] == ["b"]
    assert [e["key"] for e in audit.entries(1)] == ["a"]


def test_malformed_lines_are_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "places.log").write_text('not json\n{"key": "a"}\n')

    assert audit.entries(10) == [{"key": "a"}]


def test_place_log_prints_lines(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(audit, "_lemon_id", lambda: "A.Bee")
    _record(flags=["--yes"], reason="nope", outcome="refused")

    log_cli.cmd_log(argparse.Namespace(key="", limit=5, json=False))

    out = capsys.readouterr().out
    assert "toss refused feat session=feat by=A.Bee" in out
    assert "--yes - nope" in out


def test_a_decoding_failure_in_caller_collection_does_not_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))

    def boom():
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

    monkeypatch.setattr(audit, "caller", boom)

    audit.record("toss", "dry-run")

    assert not (tmp_path / "logs" / "places.log").exists()


def test_lemon_lookup_reads_the_attached_brief_id_and_writes_nothing(tmp_path, monkeypatch):
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as conn:
        conn.executescript(
            "CREATE TABLE session_briefs (channel TEXT, path TEXT);"
            "CREATE TABLE lemon_identities (path TEXT, lemon_id TEXT);"
            "INSERT INTO session_briefs VALUES ('claude:abc', '/b.md');"
            "INSERT INTO lemon_identities VALUES ('/b.md', 'Does a thing.WordyBin');"
        )
    before = database.read_bytes()
    monkeypatch.setattr(audit.db, "get_db_path", lambda: database)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:abc")

    assert audit._lemon_id() == "Does a thing.WordyBin"
    assert database.read_bytes() == before


def test_lemon_lookup_gives_up_quickly_while_a_writer_holds_the_database(tmp_path, monkeypatch):
    database = tmp_path / "audit.db"
    writer = sqlite3.connect(database, isolation_level=None)
    writer.execute("CREATE TABLE session_briefs (channel TEXT, path TEXT)")
    writer.execute("BEGIN EXCLUSIVE")
    monkeypatch.setattr(audit.db, "get_db_path", lambda: database)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:abc")

    started = time.monotonic()
    try:
        assert audit._lemon_id() == ""
    finally:
        writer.close()

    assert time.monotonic() - started < 2
