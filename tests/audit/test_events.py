import argparse

from lemonaid.audit import actor, cli, events
from lemonaid.places import audit as place_audit


def _as(monkeypatch, who):
    monkeypatch.setattr(
        actor, "caller", lambda by="": {"who": by or who, "via": "env", "pid": 1, "tty": ""}
    )


def test_record_appends_the_action_and_its_actor(monkeypatch):
    _as(monkeypatch, "A thing.WordyBin")

    events.record("brief-archive", "Other.LemonId", "by hand", **{"from": "/a", "to": "/b"})

    [entry] = events.entries(0)
    assert entry | {"at": "", "argv": ""} == {
        "at": "",
        "action": "brief-archive",
        "thing": "Other.LemonId",
        "why": "by hand",
        "from": "/a",
        "to": "/b",
        "argv": "",
        "who": "A thing.WordyBin",
        "via": "env",
        "pid": 1,
        "tty": "",
    }


def test_a_failure_naming_the_actor_still_records_the_action(monkeypatch):
    def boom(by=""):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

    monkeypatch.setattr(actor, "caller", boom)

    events.record("inbox-archive", "claude:x")

    [entry] = events.entries(0)
    assert entry["thing"] == "claude:x" and "actor_error" in entry


def test_entries_merge_place_events_and_filter_by_actor_and_thing(monkeypatch):
    _as(monkeypatch, "Lead.Bless")
    place_audit.record("toss", "tearing-down", key="feat/x", session="feat-x")
    _as(monkeypatch, "sam")
    events.record("brief-revive", "Child.Lunar", "by hand")
    events.record("inbox-archive", "claude:abc", "pane-gone", by="inbox watcher")

    assert [e["thing"] for e in events.entries(0)] == ["feat/x", "Child.Lunar", "claude:abc"]
    assert [e["action"] for e in events.entries(0, by="bless")] == ["toss"]
    assert [e["action"] for e in events.entries(0, thing="feat-x")] == ["toss"]
    assert [e["action"] for e in events.entries(0, by="watcher")] == ["inbox-archive"]
    assert [e["action"] for e in events.entries(1)] == ["inbox-archive"]


def test_audit_prints_one_line_per_event(monkeypatch, capsys):
    _as(monkeypatch, "sam")
    events.record("brief-archive", "Child.Lunar", "idle sweep: unused 14+ days")

    cli._cmd(argparse.Namespace(limit=5, by="", thing="", json=False))

    out = capsys.readouterr().out
    assert "brief-archive Child.Lunar by=sam via=env pid=1 - idle sweep: unused 14+ days" in out
