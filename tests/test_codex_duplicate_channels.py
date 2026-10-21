import json

import pytest

from lemonaid.brief import attached, store
from lemonaid.codex import channels, notify, utils
from lemonaid.inbox import db

_ROOT = "01999a7c-2f10-7a3e-9c41-5b2d8e0f1a11"
_TRANSIENT = "01999a7c-3b84-7d02-8e67-0c9f4a1b2c22"
_REVIEWER = "01999a7d-0000-7000-8000-000000000033"
_LOCATION = {
    "tty": "/dev/author",
    "tmux_pane_identity": ["%2", 10],
    "tmux_socket": "/tmp/server",
    "cwd": "/work/shared",
}


@pytest.fixture
def setup(monkeypatch, tmp_path):
    rollout = tmp_path / f"rollout-2026-10-20-{_ROOT}.jsonl"
    rollout.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": _ROOT, "cwd": "/work/shared"}}) + "\n"
    )
    monkeypatch.setattr(notify, "find_session_path", lambda sid: rollout if sid == _ROOT else None)
    monkeypatch.setattr(utils, "find_session_path", lambda sid: rollout if sid == _ROOT else None)
    monkeypatch.setattr(
        notify, "find_latest_session_for_cwd", lambda cwd: pytest.fail("directory is not identity")
    )
    monkeypatch.setattr(notify.hosting, "under_app_server", lambda: False)
    monkeypatch.setattr(notify, "get_tty", lambda: "/dev/author")
    monkeypatch.setattr(notify, "detect_terminal_switch_source", lambda: "tmux")
    monkeypatch.setattr(notify, "get_tmux_session_name", lambda: "shared")
    monkeypatch.setattr(notify, "get_tmux_session_order", lambda: (20, 10, 1))
    monkeypatch.setattr(notify, "get_tmux_socket", lambda: "/tmp/server")
    monkeypatch.setenv("TMUX_PANE", "%2")
    monkeypatch.setattr(notify, "get_git_branch", lambda cwd: None)
    return rollout


def _row(conn, thread, location, *, attach=False):
    row = db.add(
        conn,
        f"codex:{thread}",
        "old",
        "manual name",
        {**location, "session_id": thread, "auto_name": "original generated name"},
        switch_source="tmux",
        status="read",
    )
    if attach:
        brief = store.briefs_dir() / f"{thread}.md"
        brief.parent.mkdir(exist_ok=True, parents=True)
        brief.write_text("# test\nGroups: testing\n")
        attached.attach(conn, row.channel, brief)
    return row


def test_existing_duplicate_is_archived_without_moving_attachment(setup):
    with db.connect() as conn:
        author = _row(conn, _ROOT, _LOCATION, attach=True)
        duplicate = _row(conn, _TRANSIENT, _LOCATION)
        db.mark_unread(conn, duplicate.id)
        briefs = [tuple(r) for r in conn.execute("select * from session_briefs")]
        assert channels.repair_duplicates(conn, {_ROOT: [_LOCATION]}) == 1
        assert db.get(conn, duplicate.id).is_archived
        assert db.get(conn, author.id).is_unread
        assert briefs == [tuple(r) for r in conn.execute("select * from session_briefs")]
        assert channels.repair_duplicates(conn, {_ROOT: [_LOCATION]}) == 0


def test_attached_transient_channel_stays_attached_when_owner_notifies(setup):
    with db.connect() as conn:
        row = _row(conn, _TRANSIENT, _LOCATION, attach=True)
        briefs = [tuple(r) for r in conn.execute("select * from session_briefs")]
        channels.repair_duplicates(conn, {_ROOT: [_LOCATION]})
    notify.handle_notification(json.dumps({"thread-id": _ROOT, "cwd": "/work/shared"}))
    with db.connect() as conn:
        assert db.get(conn, row.id).metadata["session_id"] == _ROOT
        assert db.get_by_channel(conn, f"codex:{_ROOT}", unread_only=False) is None
        assert briefs == [tuple(r) for r in conn.execute("select * from session_briefs")]


def test_real_restart_with_a_rollout_keeps_its_new_channel(setup, monkeypatch, tmp_path):
    real = tmp_path / f"rollout-2026-10-20-{_TRANSIENT}.jsonl"
    real.write_text(json.dumps({"type": "session_meta", "payload": {"id": _TRANSIENT}}) + "\n")
    monkeypatch.setattr(
        notify, "find_session_path", lambda sid: real if sid == _TRANSIENT else setup
    )
    monkeypatch.setattr(
        utils, "find_session_path", lambda sid: real if sid == _TRANSIENT else setup
    )
    with db.connect() as conn:
        _row(conn, _ROOT, _LOCATION, attach=True)
    notify.handle_notification(json.dumps({"thread-id": _TRANSIENT, "cwd": "/work/shared"}))
    with db.connect() as conn:
        assert db.get_by_channel(conn, f"codex:{_TRANSIENT}", unread_only=False) is not None


def test_repair_keeps_existing_waiter_channel_and_self_lookup(setup, monkeypatch):
    from lemonaid.brief import lemon

    with db.connect() as conn:
        row = _row(conn, _TRANSIENT, _LOCATION, attach=True)
        canonical = _row(conn, _ROOT, _LOCATION)
        briefs = [tuple(r) for r in conn.execute("select * from session_briefs")]
        channels.repair_duplicates(conn, {_ROOT: [_LOCATION]})
        assert db.get(conn, canonical.id).is_archived
        assert briefs == [tuple(r) for r in conn.execute("select * from session_briefs")]
        monkeypatch.setenv("CODEX_THREAD_ID", _ROOT)
        assert lemon.self_channel(conn) == row.channel
        assert channels.for_session(conn, _ROOT) == row.channel
        db.mark_unread(conn, row.id)
    assert notify.dismiss_session(_ROOT) == 1


def test_ambiguous_attachment_is_not_reconciled(setup):
    with db.connect() as conn:
        _row(conn, _TRANSIENT, _LOCATION, attach=True)
        other = "01999a7d-0000-7000-8000-000000000099"
        _row(conn, other, _LOCATION, attach=True)
        assert channels.attached_channel(conn, _ROOT, _LOCATION) is None
        assert channels.repair_duplicates(conn, {_ROOT: [_LOCATION]}) == 0


def test_real_new_thread_is_not_archived_as_duplicate(setup, monkeypatch, tmp_path):
    real = tmp_path / f"rollout-2026-10-20-{_TRANSIENT}.jsonl"
    real.write_text("{}\n")
    monkeypatch.setattr(
        utils, "find_session_path", lambda sid: real if sid == _TRANSIENT else setup
    )
    with db.connect() as conn:
        _row(conn, _ROOT, _LOCATION, attach=True)
        newcomer = _row(conn, _TRANSIENT, _LOCATION)
        assert channels.repair_duplicates(conn, {_ROOT: [_LOCATION]}) == 0
        assert not db.get(conn, newcomer.id).is_archived


def test_handoff_token_does_not_allow_a_rolloutless_notification(setup, monkeypatch):
    with db.connect() as conn:
        _row(conn, _ROOT, _LOCATION, attach=True)
    calls = []
    monkeypatch.setenv("LEMONAID_HANDOFF_TOKEN", "launch-token")
    monkeypatch.setattr(
        notify.handoff_state, "bind_target", lambda conn, token, channel: calls.append(channel)
    )
    notify.handle_notification(json.dumps({"thread-id": _TRANSIENT, "cwd": "/work/shared"}))
    assert calls == []


def test_snoozed_attachment_does_not_get_a_second_channel(setup):
    with db.connect() as conn:
        row = _row(conn, _ROOT, _LOCATION, attach=True)
        conn.execute("UPDATE notifications SET status='snoozed' WHERE id=?", (row.id,))
        conn.commit()
    notify.handle_notification(json.dumps({"thread-id": _TRANSIENT, "cwd": "/work/shared"}))
    with db.connect() as conn:
        assert db.get_by_channel(conn, f"codex:{_TRANSIENT}", unread_only=False) is None
        assert db.get(conn, row.id).channel == f"codex:{_ROOT}"


def test_missing_hook_tty_uses_its_own_tmux_pane_for_owner_resolution(setup, monkeypatch):
    monkeypatch.setattr(notify, "get_tty", lambda: None)
    monkeypatch.setattr(notify, "get_tmux_pane_tty", lambda: "/dev/author")
    with db.connect() as conn:
        row = _row(conn, _ROOT, _LOCATION, attach=True)
    notify.handle_notification(json.dumps({"thread-id": _ROOT, "cwd": "/work/shared"}))
    with db.connect() as conn:
        assert db.get_by_channel(conn, f"codex:{_TRANSIENT}", unread_only=False) is None
        assert db.get(conn, row.id).metadata["tty"] == "/dev/author"


def test_recovered_rollout_still_filters_automatic_approval(setup, monkeypatch):
    monkeypatch.setattr(
        notify.permissions, "automatically_reviewed", lambda path, *args: path == setup
    )
    notify.handle_notification(
        json.dumps(
            {
                "session_id": _TRANSIENT,
                "cwd": "/work/shared",
                "hook_event_name": "PermissionRequest",
                "turn_id": "turn",
                "tool_name": "Bash",
            }
        )
    )
    with db.connect() as conn:
        assert db.get_active(conn) == []


@pytest.mark.parametrize("operation", ["notify", "repair"])
def test_real_restart_does_not_take_a_reconciled_alias(setup, monkeypatch, tmp_path, operation):
    real = tmp_path / f"rollout-2026-10-20-{_REVIEWER}.jsonl"
    real.write_text(json.dumps({"type": "session_meta", "payload": {"id": _REVIEWER}}) + "\n")

    def lookup(sid):
        return real if sid == _REVIEWER else setup if sid == _ROOT else None

    monkeypatch.setattr(notify, "find_session_path", lookup)
    monkeypatch.setattr(utils, "find_session_path", lookup)
    with db.connect() as conn:
        alias = _row(conn, _TRANSIENT, _LOCATION, attach=True)
        db.repair_location(conn, alias, {"session_id": _ROOT, "session_path": str(setup)})
        before = db.get(conn, alias.id)
        attachments = [tuple(r) for r in conn.execute("SELECT * FROM session_briefs")]
        if operation == "repair":
            _row(conn, _REVIEWER, {**_LOCATION, "session_path": str(real)})
            assert channels.repair_duplicates(conn, {_REVIEWER: [_LOCATION]}) == 0
    if operation == "notify":
        notify.handle_notification(json.dumps({"thread-id": _REVIEWER, "cwd": "/work/shared"}))
    with db.connect() as conn:
        newcomer = db.get_by_channel(conn, f"codex:{_REVIEWER}", unread_only=False)
        assert newcomer is not None and not newcomer.is_archived
        assert db.get(conn, alias.id) == before
        assert attachments == [tuple(r) for r in conn.execute("SELECT * FROM session_briefs")]
        assert channels.for_session(conn, _ROOT) == alias.channel
        assert channels.for_session(conn, _REVIEWER) == newcomer.channel


@pytest.mark.parametrize("phase", ["requested", "prepared", "launched", "transferred"])
def test_reconciliation_leaves_pending_handoff_channels_alone(setup, phase):
    from lemonaid.brief.handoff import state as handoff_state

    with db.connect() as conn:
        old = _row(conn, _TRANSIENT, _LOCATION, attach=True)
        path = store.briefs_dir() / f"{_TRANSIENT}.md"
        transfer = handoff_state.request(
            conn, path, old.channel, "codex", "shared", "2", "@1", "%2", "codex", 9999999999
        )
        conn.execute(
            "UPDATE brief_handoffs SET phase=?, target=? WHERE token=?",
            (phase, f"codex:{_ROOT}", transfer["token"]),
        )
        conn.commit()
        old = db.get(conn, old.id)
    # Tokenless later hooks must also respect the persistent transfer reservation.
    notify.handle_notification(json.dumps({"thread-id": _ROOT, "cwd": "/work/shared"}))
    with db.connect() as conn:
        target = db.get_by_channel(conn, f"codex:{_ROOT}", unread_only=False)
        assert target is not None
        assert db.get(conn, old.id) == old
        if phase == "transferred":
            conn.execute(
                "UPDATE session_briefs SET channel=? WHERE channel=?", (target.channel, old.channel)
            )
            conn.commit()
        before = [tuple(r) for r in conn.execute("SELECT * FROM notifications")]
        attachments = [tuple(r) for r in conn.execute("SELECT * FROM session_briefs")]
        assert channels.repair_duplicates(conn, {_ROOT: [_LOCATION]}) == 0
        assert before == [tuple(r) for r in conn.execute("SELECT * FROM notifications")]
        assert attachments == [tuple(r) for r in conn.execute("SELECT * FROM session_briefs")]


@pytest.mark.parametrize("surface", ["tmux", "wezterm", "cmux", "unknown"])
@pytest.mark.parametrize("thread", [_TRANSIENT, "short-id"])
def test_no_rollout_drops_before_db_or_terminal_inspection(setup, monkeypatch, surface, thread):
    # Recaps must not even update the parent's timestamp/unread state, much less
    # create a row that the periodic repair would archive after it flashes.
    monkeypatch.setattr(notify, "detect_terminal_switch_source", lambda: surface)
    with db.connect() as conn:
        author = _row(conn, _ROOT, _LOCATION, attach=True)
        author = db.get(conn, author.id)

    def forbidden(*args, **kwargs):
        pytest.fail("rolloutless notify must return before DB or terminal inspection")

    with monkeypatch.context() as gate:
        gate.setattr(db, "connect", forbidden)
        gate.setattr(notify, "get_tty", forbidden)
        gate.setattr(notify, "find_latest_session_for_cwd", forbidden)
        notify.handle_notification(
            json.dumps({"type": "agent-turn-complete", "thread-id": thread, "cwd": "/work/shared"})
        )
    with db.connect() as conn:
        assert db.get(conn, author.id) == author
        assert db.get_by_channel(conn, f"codex:{thread}", unread_only=False) is None


@pytest.mark.parametrize("surface", ["tmux", "wezterm", "cmux"])
def test_persistent_thread_keeps_its_row_after_terminal_move(setup, monkeypatch, surface):
    monkeypatch.setattr(notify, "detect_terminal_switch_source", lambda: surface)
    monkeypatch.setattr(notify, "get_tty", lambda: "/dev/new-terminal")
    with db.connect() as conn:
        author = _row(conn, _ROOT, _LOCATION, attach=True)
        reviewer = _row(conn, _REVIEWER, _LOCATION, attach=True)
        before = db.get(conn, reviewer.id)
        attachments = [tuple(r) for r in conn.execute("SELECT * FROM session_briefs")]
    notify.handle_notification(json.dumps({"thread-id": _ROOT, "cwd": "/work/shared"}))
    with db.connect() as conn:
        assert db.get(conn, author.id).metadata["session_id"] == _ROOT
        assert db.get(conn, author.id).metadata["tty"] == "/dev/new-terminal"
        assert db.get(conn, reviewer.id) == before
        assert attachments == [tuple(r) for r in conn.execute("SELECT * FROM session_briefs")]
