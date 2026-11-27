import json
import subprocess
import time
from pathlib import Path

from lemonaid.inbox import db
from lemonaid.openclaw import sessions
from lemonaid.watch import turns
from tests.lineage.shared import lemon

ROOM_KEY = "agent:garden:matrix:channel:!g4rd3n:grove.example"


def _listing(*keys: str) -> str:
    return json.dumps(
        {
            "count": len(keys),
            "sessions": [
                {
                    "key": key,
                    "sessionId": f"id-{n}",
                    "agentId": key.split(":")[1],
                    "kind": "group",
                    "status": "done",
                    "updatedAt": 1795617507337,
                    "lastInteractionAt": 1795617500000,
                    "totalTokens": 102356,
                    "contextTokens": 258400,
                }
                for n, key in enumerate(keys)
            ],
        }
    )


def test_parse_keys_sessions_by_session_key():
    found = sessions._parse(_listing(ROOM_KEY, "agent:main:cron:abc"))

    assert set(found) == {ROOM_KEY, "agent:main:cron:abc"}
    assert found[ROOM_KEY] == sessions.Session(
        ROOM_KEY, "id-0", "garden", "group", "done", 1795617507337, 102356, 258400, 1795617500000
    )


def test_parse_skips_entries_without_a_key():
    assert sessions._parse(json.dumps({"sessions": [{"sessionId": "x"}, {"key": ""}]})) == {}


def test_channel_and_session_key_round_trip():
    channel = sessions.channel(ROOM_KEY)

    assert channel == f"openclaw:{ROOM_KEY}"
    assert sessions.session_key(channel) == ROOM_KEY
    assert sessions.session_key("codex:abc") == ""


def test_hosted_codex_home_is_only_openclaws(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    inside = tmp_path / ".openclaw/agents/main/agent/codex-home"

    monkeypatch.setenv("CODEX_HOME", str(inside))
    assert sessions.hosted_codex_home() == inside

    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    assert sessions.hosted_codex_home() is None

    monkeypatch.delenv("CODEX_HOME")
    assert sessions.hosted_codex_home() is None


def test_listed_reads_the_cli(monkeypatch):
    calls = []

    def run(argv, **_):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, _listing(ROOM_KEY), "")

    monkeypatch.setattr(sessions.subprocess, "run", run)

    assert list(sessions.listed("openclaw")) == [ROOM_KEY]
    assert calls == [["openclaw", "sessions", "--all-agents", "--limit", "all", "--json"]]


def test_listed_raises_unavailable_on_failure(monkeypatch):
    monkeypatch.setattr(
        sessions.subprocess,
        "run",
        lambda argv, **_: subprocess.CompletedProcess(argv, 1, "", "gateway down"),
    )

    try:
        sessions.listed("openclaw")
    except sessions.Unavailable as error:
        assert "gateway down" in str(error)
    else:
        raise AssertionError("expected Unavailable")


def test_archived_asks_the_gateway_for_archived_sessions_and_their_reasons(monkeypatch):
    calls = []
    listing = {"sessions": [{"key": ROOM_KEY, "archiveReason": "manual"}, {"key": "old"}]}

    def run(argv, **_):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps(listing), "")

    monkeypatch.setattr(sessions.subprocess, "run", run)

    assert sessions.archived("openclaw") == {ROOM_KEY: "manual", "old": ""}
    assert calls[0][1:4] == ["gateway", "call", "sessions.list"]
    assert json.loads(calls[0][-1])["archived"] is True


def test_exists_checker_lists_at_most_once_per_interval(monkeypatch):
    listings = [{ROOM_KEY: None}, {}]
    monkeypatch.setattr(sessions, "listed", lambda executable: listings.pop(0))
    now = [100.0]
    monkeypatch.setattr(sessions.time, "monotonic", lambda: now[0])
    exists = sessions.exists_checker("openclaw", max_age=60)

    assert exists(ROOM_KEY) is True
    now[0] += 30
    assert exists(ROOM_KEY) is True  # not listed again yet
    now[0] += 30
    assert exists(ROOM_KEY) is False


def test_exists_checker_says_none_when_the_gateway_cant(monkeypatch):
    def unavailable(executable):
        raise sessions.Unavailable("down")

    monkeypatch.setattr(sessions, "listed", unavailable)

    assert sessions.exists_checker("openclaw", max_age=60)(ROOM_KEY) is None


def test_cli_falls_back_to_the_installers_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sessions.shutil, "which", lambda name: None)

    assert sessions.cli() == str(Path(tmp_path) / ".local/bin/openclaw")


def test_recorded_turns_reads_the_observer_s_record_from_the_inbox():
    lemon("garden", sessions.channel(ROOM_KEY))
    latest = sessions.recorded_turns(ROOM_KEY)
    assert latest() is None  # nothing observed yet: nobody can say

    now = float(int(time.time()))  # whole seconds, which JSON keeps exactly
    with db.connect() as conn:
        db.record_turn_times(conn, sessions.channel(ROOM_KEY), now, now - 5, now - 60)
    assert latest() == turns.Turn(True, now - 5, now - 60)

    with db.connect() as conn:
        db.record_turn_times(conn, sessions.channel(ROOM_KEY), None, now - 5, now)
    assert latest() == turns.Turn(False, now - 5, now)


def test_a_turn_recorded_long_ago_is_not_still_running():
    lemon("garden", sessions.channel(ROOM_KEY))
    with db.connect() as conn:
        db.record_turn_times(conn, sessions.channel(ROOM_KEY), time.time() - 3600, 1.0, 0)

    assert sessions.recorded_turns(ROOM_KEY)() == turns.Turn(False, 1.0, 0)
