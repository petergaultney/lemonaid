"""A lemon follows its OpenClaw session's archive state through `sync`."""

import time

from lemonaid.front_end import chat
from lemonaid.inbox import db, ended
from lemonaid.openclaw import archived, lemons, sessions, sync

NOW = 1_800_000_000_000
MEYER = sync.Agent("main", "Ada", "/srv/agent-home", True)
AGENTS = {"main": MEYER}
SIGNAL = "agent:main:signal:direct:uuid:abc"
ROOM = "agent:main:matrix:channel:!r00mA1b2:grove.example"


def _session(key: str) -> sessions.Session:
    return sessions.Session(key, "id", "main", "direct", "done", NOW, 0, 0)


def _row(key: str) -> db.Notification:
    with db.connect() as conn:
        return db.get_by_channel(conn, sessions.channel(key), unread_only=False)


def test_archiving_in_openclaw_archives_a_lemon_its_session_registered():
    with db.connect() as conn:
        lemons.register(conn, _session(SIGNAL), "thread-1", None, "/home/me", chat.NAME)
        _, gone = sync.sync(
            conn,
            [_session(SIGNAL)],
            AGENTS,
            chat.NAME,
            {SIGNAL: "manual"},
            {SIGNAL: _session(SIGNAL)},
        )

    row = _row(SIGNAL)
    assert gone == [sessions.channel(SIGNAL)]
    assert row.is_archived
    assert row.metadata["ended"]["by"] == archived.BY
    assert "manual" in row.metadata["ended"]["detail"]


def test_restoring_in_openclaw_brings_the_lemon_back_as_it_was():
    with db.connect() as conn:
        lemons.register(conn, _session(SIGNAL), "thread-1", None, "/home/me", chat.NAME)
        sync.sync(conn, [], AGENTS, chat.NAME, {SIGNAL: "manual"}, {SIGNAL: _session(SIGNAL)})
        back, _ = sync.sync(
            conn, [_session(SIGNAL)], AGENTS, chat.NAME, {}, {SIGNAL: _session(SIGNAL)}
        )

    row = _row(SIGNAL)
    assert back == [sessions.channel(SIGNAL)]
    assert not row.is_archived
    assert row.metadata["codex_thread"] == "thread-1"
    assert "ended" not in row.metadata


def test_a_lemon_archived_by_hand_stays_archived_until_its_session_has_a_message():
    with db.connect() as conn:
        lemons.register(conn, _session(SIGNAL), "thread-1", None, "/home/me", chat.NAME)
        db.archive_channel(conn, sessions.channel(SIGNAL), "done", cause="archived", by="user")
        back, _ = sync.sync(
            conn, [_session(SIGNAL)], AGENTS, chat.NAME, {}, {SIGNAL: _session(SIGNAL)}
        )

    assert back == []
    assert _row(SIGNAL).is_archived


def test_an_archived_conversation_is_not_added_and_a_deleted_one_is_not_restored():
    with db.connect() as conn:
        added, _ = sync.sync(
            conn, [_session(ROOM)], AGENTS, chat.NAME, {ROOM: "manual"}, {ROOM: _session(ROOM)}
        )
        lemons.register(conn, _session(SIGNAL), "thread-1", None, "/home/me", chat.NAME)
        sync.sync(conn, [], AGENTS, chat.NAME, {SIGNAL: "manual"}, {SIGNAL: _session(SIGNAL)})
        back, _ = sync.sync(conn, [], AGENTS, chat.NAME, {}, {})

    assert (added, back) == ([], [])
    assert _row(ROOM) is None
    assert _row(SIGNAL).is_archived


def test_a_message_after_an_archive_by_hand_brings_the_lemon_back():
    with db.connect() as conn:
        lemons.register(conn, _session(SIGNAL), "thread-1", None, "/home/me", chat.NAME)
        db.archive_channel(conn, sessions.channel(SIGNAL), "done", cause="archived", by="user")
        later = _session(SIGNAL)._replace(interacted_ms=int((time.time() + 60) * 1000))
        back, _ = sync.sync(conn, [later], AGENTS, chat.NAME, {}, {SIGNAL: later})

    assert back == [sessions.channel(SIGNAL)]
    assert not _row(SIGNAL).is_archived


def test_a_lemon_a_handoff_replaced_stays_archived_when_its_old_session_answers():
    with db.connect() as conn:
        lemons.register(conn, _session(SIGNAL), "thread-1", None, "/home/me", chat.NAME)
        db.archive_channel(
            conn, sessions.channel(SIGNAL), "handed off", cause=ended.REPLACED, by="handoff"
        )
        later = _session(SIGNAL)._replace(interacted_ms=int((time.time() + 60) * 1000))
        back, _ = sync.sync(conn, [later], AGENTS, chat.NAME, {}, {SIGNAL: later})

    assert back == []
    assert _row(SIGNAL).is_archived
