import argparse

from lemonaid.audit import actor
from lemonaid.places import audit, log_cli


def _record(action="toss", outcome="tearing-down", key="feat", **kw):
    audit.record(action, outcome, key=key, session=kw.pop("session", "feat"), **kw)


def _as(monkeypatch, who):
    monkeypatch.setattr(
        actor, "caller", lambda by="": {"who": who, "via": "env", "pid": 7, "parent": "", "tty": ""}
    )


def test_record_appends_a_json_line_with_the_caller(monkeypatch):
    _as(monkeypatch, "Some thing.SwearDig")

    _record(flags=["--yes"], reason="why", directory="/d")

    [entry] = audit.entries(0)
    assert entry | {"at": ""} == {
        "at": "",
        "action": "toss",
        "outcome": "tearing-down",
        "key": "feat",
        "dir": "/d",
        "session": "feat",
        "flags": ["--yes"],
        "reason": "why",
        "who": "Some thing.SwearDig",
        "via": "env",
        "pid": 7,
        "parent": "",
        "tty": "",
    }
    assert entry["at"][-6] in "+-"


def test_entries_filter_by_key_or_session_and_limit(monkeypatch):
    _as(monkeypatch, "")
    _record(key="a", session="s1")
    _record(key="b", session="s2")
    _record(key="a", session="s1", outcome="declined")

    assert [e["outcome"] for e in audit.entries(10, "a")] == ["tearing-down", "declined"]
    assert [e["key"] for e in audit.entries(10, "s2")] == ["b"]
    assert [e["key"] for e in audit.entries(1)] == ["a"]


def test_place_log_prints_lines(monkeypatch, capsys):
    _as(monkeypatch, "A.Bee")
    _record(flags=["--yes"], reason="nope", outcome="refused")

    log_cli.cmd_log(argparse.Namespace(key="", limit=5, json=False))

    out = capsys.readouterr().out
    assert "toss refused feat session=feat by=A.Bee" in out
    assert "--yes - nope" in out


def test_a_decoding_failure_naming_the_caller_still_records_the_event(monkeypatch):
    def boom(by=""):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

    monkeypatch.setattr(actor, "caller", boom)

    audit.record("toss", "dry-run")

    assert [(e["outcome"], e["who"]) for e in audit.entries(0)] == [("dry-run", "unknown")]
