"""Every recent OpenClaw conversation as a lemon: which sessions, how they're named, and when
the rows this adds are archived."""

import sqlite3
import time

from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.front_end import chat
from lemonaid.inbox import db
from lemonaid.openclaw import lemons, sessions, sync

NOW = 1_800_000_000_000
DAY = 86_400_000
MEYER = sync.Agent("main", "Ada", "/srv/agent-home", True)
BARN = sync.Agent("garden", "garden", "/srv/garden", False)
AGENTS = {"main": MEYER, "garden": BARN}
ROOM = "agent:main:matrix:channel:!r00mA1b2:grove.example"
SIGNAL = "agent:main:signal:direct:uuid:abc"
BARN_ROOM = "agent:garden:matrix:channel:!g4rd3n:grove.example"
CRON = "agent:main:cron:3fa3"
THREAD = f"{ROOM}:thread:a5a3"


def _session(key: str, age_days: float = 1) -> sessions.Session:
    return sessions.Session(
        key, "id", key.split(":")[1], "group", "done", int(NOW - age_days * DAY), 0, 0
    )


def _rows() -> dict[str, db.Notification]:
    with db.connect() as conn:
        return {
            channel: db.get_by_channel(conn, channel, unread_only=False)
            for (channel,) in conn.execute("SELECT channel FROM notifications").fetchall()
        }


def test_conversations_are_recent_chats_and_leave_out_cron_runs_and_threads():
    found = {key: _session(key) for key in (ROOM, SIGNAL, CRON, THREAD)} | {
        "old": _session(SIGNAL, 30)._replace(key="agent:main:signal:direct:old")
    }

    kept = sync.conversations(found, NOW, 14 * DAY, sync.CHATS)

    assert {each.key for each in kept} == {ROOM, SIGNAL}


def test_sync_adds_each_conversation_named_for_its_agent_in_its_workspace():
    with db.connect() as conn:
        added, archived = sync.sync(
            conn,
            [_session(ROOM), _session(SIGNAL), _session(BARN_ROOM)],
            AGENTS,
            chat.NAME,
            {},
            {},
        )

    assert (sorted(added), archived) == (
        sorted(sessions.channel(key) for key in (ROOM, SIGNAL, BARN_ROOM)),
        [],
    )
    rows = _rows()
    assert rows[sessions.channel(ROOM)].name == "Ada - room r00mA1"
    assert rows[sessions.channel(SIGNAL)].name == "Ada - Signal"
    assert rows[sessions.channel(BARN_ROOM)].name == "garden"
    assert rows[sessions.channel(BARN_ROOM)].metadata["cwd"] == "/srv/garden"
    assert rows[sessions.channel(ROOM)].switch_source == chat.NAME


def test_sync_leaves_a_session_that_registered_itself_alone():
    with db.connect() as conn:
        lemons.register(conn, _session(SIGNAL), "thread-1", None, "/home/me", chat.NAME)
        added, _ = sync.sync(conn, [_session(SIGNAL)], AGENTS, chat.NAME, {}, {})
        added_later, archived = sync.sync(conn, [], AGENTS, chat.NAME, {}, {})

    assert (added, added_later, archived) == ([], [], [])
    assert _rows()[sessions.channel(SIGNAL)].metadata["codex_thread"] == "thread-1"


def test_a_quiet_conversation_is_archived_unless_it_has_a_brief(tmp_path):
    with db.connect() as conn:
        sync.sync(conn, [_session(ROOM), _session(SIGNAL)], AGENTS, chat.NAME, {}, {})
        path = brief_store.briefs_dir() / "room.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Room\n")
        attached.attach(conn, sessions.channel(ROOM), path)

        _, archived = sync.sync(conn, [], AGENTS, chat.NAME, {}, {})

    assert archived == [sessions.channel(SIGNAL)]
    assert _rows()[sessions.channel(SIGNAL)].is_archived


def test_a_conversation_that_wakes_again_comes_back():
    with db.connect() as conn:
        sync.sync(conn, [_session(SIGNAL)], AGENTS, chat.NAME, {}, {})
        sync.sync(conn, [], AGENTS, chat.NAME, {}, {})
        added, _ = sync.sync(conn, [_session(SIGNAL)], AGENTS, chat.NAME, {}, {})

    assert added == [sessions.channel(SIGNAL)]
    assert not _rows()[sessions.channel(SIGNAL)].is_archived


def test_a_conversations_lemon_is_dated_by_its_last_message():
    an_hour_ago = int(time.time() * 1000) - 3_600_000
    spoke = _session(SIGNAL)._replace(interacted_ms=an_hour_ago)
    with db.connect() as conn:
        sync.sync(conn, [spoke], AGENTS, chat.NAME, {}, {SIGNAL: spoke})
        added = _rows()[sessions.channel(SIGNAL)].created_at
        sync.sync(conn, [spoke], AGENTS, chat.NAME, {}, {SIGNAL: spoke._replace(interacted_ms=NOW)})
        sync.sync(conn, [spoke], AGENTS, chat.NAME, {}, {SIGNAL: spoke})

    row = _rows()[sessions.channel(SIGNAL)]
    assert added == an_hour_ago / 1000
    assert (row.created_at, row.status) == (NOW / 1000, "read")  # never back, status as added


def test_a_thread_the_sync_added_is_archived_and_its_messages_bring_it_back_no_more():
    with db.connect() as conn:
        sync.sync(conn, [_session(THREAD)], AGENTS, chat.NAME, {}, {})
        talking = _session(THREAD)._replace(interacted_ms=NOW * 2)

        _, archived = sync.sync(conn, [], AGENTS, chat.NAME, {}, {THREAD: talking})
        again = sync.sync(conn, [], AGENTS, chat.NAME, {}, {THREAD: talking})

    assert (archived, again) == ([sessions.channel(THREAD)], ([], []))
    assert _rows()[sessions.channel(THREAD)].is_archived


def test_agents_reads_the_cli(tmp_path):
    cli = tmp_path / "openclaw"
    cli.write_text(
        "#!/bin/sh\n"
        'echo \'[{"id": "main", "identityName": "Ada", "workspace": "/srv/agent-home", "isDefault": true},'
        ' {"id": "garden", "name": "garden", "workspace": "/srv/garden"}]\'\n'
    )
    cli.chmod(0o755)

    assert sync.agents(str(cli)) == AGENTS


def test_a_conversation_someone_archived_stays_archived():
    with db.connect() as conn:
        sync.sync(conn, [_session(SIGNAL)], AGENTS, chat.NAME, {}, {})
        db.archive_channel(conn, sessions.channel(SIGNAL), "stale", cause="archived", by="grove")
        added, _ = sync.sync(conn, [_session(SIGNAL)], AGENTS, chat.NAME, {}, {})

    assert added == []
    assert _rows()[sessions.channel(SIGNAL)].is_archived


def test_a_session_that_registers_itself_after_the_sync_added_it_is_not_archived():
    with db.connect() as conn:
        sync.sync(conn, [_session(SIGNAL)], AGENTS, chat.NAME, {}, {})
    with db.connect() as other:
        lemons.register(other, _session(SIGNAL), "thread-1", None, "/home/me", chat.NAME)
    with db.connect() as conn:
        _, archived = sync.sync(conn, [], AGENTS, chat.NAME, {}, {})

    assert archived == []
    assert _rows()[sessions.channel(SIGNAL)].metadata["codex_thread"] == "thread-1"


def test_the_sync_holds_the_write_lock_from_its_check_to_its_write(monkeypatch):
    seen = []
    register = lemons.register

    def register_while_locked(conn, *args):
        with db.connect(timeout=0) as other:
            try:
                other.execute("UPDATE notifications SET name = name")
            except sqlite3.OperationalError as error:
                seen.append(str(error))
        return register(conn, *args)

    monkeypatch.setattr(lemons, "register", register_while_locked)
    with db.connect() as conn:
        sync.sync(conn, [_session(SIGNAL)], AGENTS, chat.NAME, {}, {})

    assert seen == ["database is locked"]
