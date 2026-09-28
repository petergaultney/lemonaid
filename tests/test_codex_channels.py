"""Codex threads started within a minute of each other get channels of their own."""

import json
import sqlite3
from pathlib import Path

import pytest

from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.codex import notify, utils, watcher
from lemonaid.inbox import db, emoji
from lemonaid.inbox.migrations import m010_full_codex_channels

# UUIDv7 ids from the same minute share their leading timestamp digits.
_THREAD_A = "01999a7c-2f10-7a3e-9c41-5b2d8e0f1a11"
_THREAD_B = "01999a7c-3b84-7d02-8e67-0c9f4a1b2c22"
_THREAD_C = "01999a7d-0000-7000-8000-000000000033"


@pytest.fixture(autouse=True)
def _no_rollouts(monkeypatch, tmp_path):
    monkeypatch.setattr(notify, "find_latest_session_for_cwd", lambda cwd: None)
    monkeypatch.setattr(notify, "find_session_path", lambda session_id: None)
    monkeypatch.setattr(watcher, "get_sessions_root", lambda: tmp_path / "no-sessions")
    monkeypatch.setattr(utils, "get_sessions_root", lambda: tmp_path / "sessions")
    monkeypatch.delenv("TMUX_PANE", raising=False)


def _notify(thread: str, cwd: str) -> None:
    notify.handle_notification(json.dumps({"thread-id": thread, "cwd": cwd}))


def _channels(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[0] for row in conn.execute(f"SELECT channel FROM {table}")}


def test_threads_sharing_a_prefix_keep_separate_rows_and_attachments():
    assert _THREAD_A[:8] == _THREAD_B[:8]
    brief = brief_store.briefs_dir() / "hq.md"
    brief.parent.mkdir(parents=True)
    brief.write_text("# hq\n")

    _notify(_THREAD_A, "/work/hq")
    with db.connect() as conn:
        attached.attach(conn, f"codex:{_THREAD_A}", brief)
        emoji.set_emoji(conn, f"codex:{_THREAD_A}", "🍋")
    _notify(_THREAD_B, "/work/reviewer")

    with db.connect() as conn:
        cwds = dict(
            conn.execute("SELECT channel, json_extract(metadata, '$.cwd') FROM notifications")
        )
        assert cwds == {f"codex:{_THREAD_A}": "/work/hq", f"codex:{_THREAD_B}": "/work/reviewer"}
        assert attached.by_channel(conn, [f"codex:{_THREAD_B}"]) == {}
        assert _channels(conn, "session_emoji") == {f"codex:{_THREAD_A}"}


def _database_before_full_channels(path: Path) -> None:
    """Rows as the release before full Codex channels wrote them."""
    with db.connect(path):
        pass
    rows = [
        (f"codex:{_THREAD_A[:8]}", {"session_id": _THREAD_A, "cwd": "/work/hq"}),
        (  # the channel came from a turn id; the rollout names the thread
            "codex:01a0cb50",
            {
                "session_id": "01a0cb50",
                "session_path": f"/s/rollout-2026-09-28T10-00-00-{_THREAD_C}.jsonl",
            },
        ),
        ("codex:0199aaaa", {"cwd": "/work/no-thread-id"}),
        ("claude:1a2b3c4d", {"session_id": "1a2b3c4d-0000-0000-0000-000000000000"}),
    ]
    conn = sqlite3.connect(path)
    for at, (channel, metadata) in enumerate(rows):
        conn.execute(
            "INSERT INTO notifications (channel, message, name, metadata, created_at, status)"
            " VALUES (?, '', ?, ?, ?, 'read')",
            (channel, f"name of {channel}", json.dumps(metadata), at),
        )
        conn.execute("INSERT INTO pins (channel, position) VALUES (?, ?)", (channel, at))
        conn.execute("INSERT INTO session_emoji VALUES (?, '🍋', 1)", (channel,))
        conn.execute("INSERT INTO session_briefs VALUES (?, ?, 1)", (channel, f"/b/{at}.md"))
    conn.execute(f"PRAGMA user_version = {m010_full_codex_channels.VERSION - 1}")
    conn.commit()
    conn.close()
    db._initialized_dbs.discard(path)


def test_upgrade_moves_short_codex_channels_to_the_full_thread_id(tmp_path):
    path = tmp_path / "upgrade.db"
    _database_before_full_channels(path)

    with db.connect(path) as conn:
        expected = {
            f"codex:{_THREAD_A}",
            f"codex:{_THREAD_C}",
            "codex:0199aaaa",
            "claude:1a2b3c4d",
        }
        for table in ("notifications", "pins", "session_emoji", "session_briefs"):
            assert _channels(conn, table) == expected, table
        assert (
            dict(conn.execute("SELECT channel, path FROM session_briefs"))[f"codex:{_THREAD_A}"]
            == "/b/0.md"
        )
        assert (
            dict(conn.execute("SELECT channel, name FROM notifications"))[f"codex:{_THREAD_A}"]
            == f"name of codex:{_THREAD_A[:8]}"
        )


def test_upgraded_thread_keeps_its_row_and_brief_when_it_notifies_again(tmp_path, monkeypatch):
    path = tmp_path / "upgrade.db"
    _database_before_full_channels(path)
    monkeypatch.setattr(db, "get_db_path", lambda: path)

    _notify(_THREAD_A, "/work/hq")
    _notify(_THREAD_B, "/work/reviewer")

    with db.connect() as conn:
        codex = [
            c
            for (c,) in conn.execute("SELECT channel FROM notifications")
            if c.startswith("codex:01999a7c")
        ]
        assert sorted(codex) == [f"codex:{_THREAD_A}", f"codex:{_THREAD_B}"]
        assert attached.by_channel(conn, [f"codex:{_THREAD_A}", f"codex:{_THREAD_B}"]) == {
            f"codex:{_THREAD_A}": Path("/b/0.md")
        }


def test_a_full_id_without_a_rollout_does_not_borrow_a_siblings(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    sibling = sessions / f"rollout-2026-09-28T10-00-00-{_THREAD_B}.jsonl"
    sibling.write_text("{}\n")
    monkeypatch.setattr(watcher, "get_sessions_root", lambda: sessions)
    monkeypatch.setattr(watcher, "find_latest_session_for_cwd", lambda cwd: sibling)

    assert watcher.get_session_path(_THREAD_A, "/work/hq") is None
    assert watcher.get_session_path(_THREAD_B, "/work/hq") == sibling


def _database_at_version_9(path: Path, rows: list[tuple[str, dict]]) -> sqlite3.Connection:
    with db.connect(path):
        pass
    conn = sqlite3.connect(path)
    for at, (channel, metadata) in enumerate(rows):
        conn.execute(
            "INSERT INTO notifications (channel, message, name, metadata, created_at, status)"
            " VALUES (?, '', ?, ?, ?, 'read')",
            (channel, f"row {at}", json.dumps(metadata), at),
        )
    conn.execute(f"PRAGMA user_version = {m010_full_codex_channels.VERSION - 1}")
    return conn


def _upgrade(path: Path, conn: sqlite3.Connection) -> None:
    conn.commit()
    conn.close()
    db._initialized_dbs.discard(path)
    with db.connect(path):
        pass


def test_a_short_row_merges_into_an_existing_full_channel(tmp_path):
    path = tmp_path / "both.db"
    conn = _database_at_version_9(
        path,
        [
            (f"codex:{_THREAD_A[:8]}", {"session_id": _THREAD_A}),
            (f"codex:{_THREAD_A}", {"session_id": _THREAD_A}),
        ],
    )
    conn.execute(
        "INSERT INTO session_briefs VALUES (?, '/b/short.md', 1)", (f"codex:{_THREAD_A[:8]}",)
    )
    conn.execute("INSERT INTO session_emoji VALUES (?, '🍋', 1)", (f"codex:{_THREAD_A[:8]}",))
    conn.execute("INSERT INTO session_emoji VALUES (?, '🧪', 1)", (f"codex:{_THREAD_A}",))
    _upgrade(path, conn)

    with sqlite3.connect(path) as conn:
        assert dict(conn.execute("SELECT channel, path FROM session_briefs")) == {
            f"codex:{_THREAD_A}": "/b/short.md"
        }
        assert dict(conn.execute("SELECT channel, emoji FROM session_emoji")) == {
            f"codex:{_THREAD_A}": "🧪"
        }
        assert list(
            conn.execute("SELECT name, channel, status FROM notifications ORDER BY id")
        ) == [
            ("row 0", f"codex:{_THREAD_A}", "archived"),
            ("row 1", f"codex:{_THREAD_A}", "read"),
        ]


@pytest.mark.parametrize("full_status", ["archived", "read"])
def test_a_newer_unread_short_row_stays_the_live_row(tmp_path, full_status):
    path = tmp_path / "short-newer.db"
    conn = _database_at_version_9(
        path,
        [
            (f"codex:{_THREAD_A}", {"session_id": _THREAD_A}),
            (f"codex:{_THREAD_A[:8]}", {"session_id": _THREAD_A}),
        ],
    )
    conn.execute("UPDATE notifications SET status = ? WHERE name = 'row 0'", (full_status,))
    conn.execute("UPDATE notifications SET status = 'unread' WHERE name = 'row 1'")
    _upgrade(path, conn)

    with db.connect(path) as conn:
        live = db.get_by_channel(conn, f"codex:{_THREAD_A}")
        assert live is not None and live.name == "row 1"
        assert [n.name for n in db.get_active(conn) if n.channel == f"codex:{_THREAD_A}"] == [
            "row 1"
        ]


def test_state_stays_when_the_newest_row_names_no_thread(tmp_path):
    path = tmp_path / "unknown-newest.db"
    conn = _database_at_version_9(
        path,
        [
            (f"codex:{_THREAD_A[:8]}", {"session_id": _THREAD_A}),
            (f"codex:{_THREAD_A[:8]}", {"cwd": "/work/unknown"}),
        ],
    )
    conn.execute(
        "INSERT INTO session_briefs VALUES (?, '/b/short.md', 1)", (f"codex:{_THREAD_A[:8]}",)
    )
    _upgrade(path, conn)

    with sqlite3.connect(path) as conn:
        assert dict(conn.execute("SELECT channel, path FROM session_briefs")) == {
            f"codex:{_THREAD_A[:8]}": "/b/short.md"
        }


def test_a_turn_id_row_records_the_rollouts_thread(tmp_path):
    path = tmp_path / "turn-id.db"
    rollout = f"/s/rollout-2026-09-28T10-00-00-{_THREAD_C}.jsonl"
    conn = _database_at_version_9(
        path,
        [
            (
                "codex:01a0cb50",
                {"session_id": "01a0cb50-eb7f-7233-80b2-ef793653653a", "session_path": rollout},
            )
        ],
    )
    _upgrade(path, conn)

    with sqlite3.connect(path) as conn:
        channel, metadata = conn.execute("SELECT channel, metadata FROM notifications").fetchone()
    assert channel == f"codex:{_THREAD_C}"
    assert json.loads(metadata)["session_id"] == _THREAD_C


def _rollout(sessions: Path, thread: str, **meta: object) -> Path:
    path = sessions / "2026" / "09" / "22" / f"rollout-2026-09-22T17-35-20-{thread}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "session_meta", "payload": {"id": thread, **meta}}) + "\n")
    return path


def test_a_reviewers_row_on_its_parents_channel_moves_to_the_parent(tmp_path):
    root = "01a0ca2f-b94c-7322-b662-e7f20f7c862f"
    guardian = "01a0ca2f-b998-7c12-9b91-4568d8e5b3a4"
    sessions = tmp_path / "sessions"
    root_rollout = _rollout(sessions, root, source="cli")
    guardian_rollout = _rollout(
        sessions,
        guardian,
        session_id=root,
        parent_thread_id=root,
        source={"subagent": {"other": "guardian"}},
    )
    path = tmp_path / "hq.db"
    conn = _database_at_version_9(
        path,
        [("codex:01a0ca2f", {"session_id": guardian, "session_path": str(guardian_rollout)})],
    )
    conn.execute("INSERT INTO session_briefs VALUES ('codex:01a0ca2f', '/b/hq.md', 1)")
    _upgrade(path, conn)

    with sqlite3.connect(path) as conn:
        channel, metadata = conn.execute("SELECT channel, metadata FROM notifications").fetchone()
        assert dict(conn.execute("SELECT channel, path FROM session_briefs")) == {
            f"codex:{root}": "/b/hq.md"
        }
    assert channel == f"codex:{root}"
    assert json.loads(metadata)["session_id"] == root
    assert json.loads(metadata)["session_path"] == str(root_rollout)


def test_a_spawned_thread_on_its_own_channel_stays_there(tmp_path):
    root = "01a0ca2f-b94c-7322-b662-e7f20f7c862f"
    subagent = "01a0e8ca-9e01-74d1-99f6-5f302c6cfd7c"
    sessions = tmp_path / "sessions"
    _rollout(sessions, root, source="cli")
    _rollout(sessions, subagent, session_id=root, parent_thread_id=root)
    path = tmp_path / "subagent.db"
    conn = _database_at_version_9(
        path,
        [
            (f"codex:{root[:8]}", {"session_id": root}),
            (f"codex:{subagent[:8]}", {"session_id": subagent}),
        ],
    )
    conn.execute("UPDATE notifications SET status = 'archived' WHERE name = 'row 1'")
    _upgrade(path, conn)

    with sqlite3.connect(path) as conn:
        assert list(conn.execute("SELECT channel, status FROM notifications ORDER BY id")) == [
            (f"codex:{root}", "read"),
            (f"codex:{subagent}", "archived"),
        ]
