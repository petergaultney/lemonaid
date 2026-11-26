"""Every OpenClaw lemon finds itself by the Codex thread OpenClaw's Codex plugin records for
its session, without registering."""

import json
import sqlite3

from lemonaid.front_end import chat
from lemonaid.inbox import db
from lemonaid.openclaw import lemons, sessions, sync, threads

AGENTS = {"main": sync.Agent("main", "Ada", "/srv/agent-home", True)}
ROOM = "agent:main:matrix:channel:!r00mA1b2:grove.example"
DAM = "agent:main:matrix:channel:!d4mR00m:grove.example"


def _session(key: str, session_id: str) -> sessions.Session:
    return sessions.Session(key, session_id, "main", "group", "done", 1, 0, 0)


def _state(path, bindings: dict[str, str], extra: list[str] = ()) -> None:
    with sqlite3.connect(path) as state:
        state.execute(
            "CREATE TABLE plugin_state_entries (plugin_id TEXT, namespace TEXT, entry_key TEXT,"
            " value_json TEXT, created_at INTEGER, expires_at INTEGER)"
        )
        values = [
            json.dumps(
                {
                    "version": 1,
                    "state": "active",
                    "binding": {
                        "threadId": thread,
                        "rolloutPath": f"/srv/codex-home/sessions/2026/11/rollout-{thread}.jsonl",
                    },
                    "sessionId": session_id,
                }
            )
            for session_id, thread in bindings.items()
        ]
        state.executemany(
            "INSERT INTO plugin_state_entries VALUES"
            " ('codex', 'app-server-thread-bindings', ?, ?, 0, NULL)",
            [(str(i), value) for i, value in enumerate([*values, *extra])],
        )


def test_each_lemon_is_bound_to_its_sessions_thread_and_finds_itself(tmp_path, monkeypatch):
    _state(tmp_path / "state.sqlite", {"s-room": "thread-room", "s-dam": "thread-dam"})
    found = {ROOM: _session(ROOM, "s-room"), DAM: _session(DAM, "s-dam")}
    with db.connect() as conn:
        sync.sync(
            conn,
            found.values(),
            AGENTS,
            chat.NAME,
            {},
            found,
            threads.running(tmp_path / "state.sqlite"),
        )
        monkeypatch.setenv("CODEX_THREAD_ID", "thread-dam")
        assert lemons.self_channel(conn) == sessions.channel(DAM)
        row = db.get_by_channel(conn, sessions.channel(DAM), unread_only=False)

    assert row.metadata["codex_home"] == "/srv/codex-home"


def test_a_thread_moves_to_the_session_now_running_it():
    with db.connect() as conn:
        lemons.register(conn, _session(ROOM, "s-room"), "thread-1", None, "/srv", chat.NAME)
        sync.sync(conn, [_session(DAM, "s-dam")], AGENTS, chat.NAME, {}, {})
        bound = threads.bind(
            conn, [_session(DAM, "s-dam")], {"s-dam": threads.Thread("thread-1", "")}
        )
        again = threads.bind(
            conn, [_session(DAM, "s-dam")], {"s-dam": threads.Thread("thread-1", "")}
        )

        assert (bound, again) == ([sessions.channel(DAM)], [])
        assert lemons.by_thread(conn, "thread-1") == sessions.channel(DAM)
        room = db.get_by_channel(conn, sessions.channel(ROOM), unread_only=False)

    assert room.metadata["codex_thread"] == ""


def test_an_unreadable_record_leaves_lemons_to_register(tmp_path):
    _state(tmp_path / "state.sqlite", {"s-room": "thread-room"}, extra=["not json"])

    assert threads.running(tmp_path / "state.sqlite") == {}
    assert threads.running(tmp_path / "missing.sqlite") == {}
