"""A Claude lemon with a brief cannot end its turn until its inbox waiter holds the lock."""

import argparse
import json
import threading
import time
from pathlib import Path

import pytest

from lemonaid.brief import attached, handoff_state, identity
from lemonaid.brief import store as brief_store
from lemonaid.claude import install_hooks, waiter_check
from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.messages import cli, store, waiter
from lemonaid.watch import briefs_cli, briefs_events, children_waiter, waiter_lock

_SESSION = "abcd1234-0000-0000-0000-000000000000"


@pytest.fixture(autouse=True)
def _no_inherited_session_identity(monkeypatch):
    for name in ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)


def _briefed(status: str = "working") -> Path:
    path = brief_store.briefs_dir() / "lemon.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# lemon\n\nStatus: {status}\n")
    with db.connect() as conn:
        db.add(conn, "claude:abcd1234", "", metadata={"session_id": _SESSION})
        attached.attach(conn, "claude:abcd1234", path)
        return store.inbox_for_id(identity.ensure(conn, path))


def _stop(capsys, **extra) -> dict | None:
    waiter_check.handle(json.dumps({"session_id": _SESSION, **extra}), grace=0.0)
    out = capsys.readouterr().out
    return json.loads(out) if out else None


def test_a_lemon_without_a_brief_stops_freely(capsys):
    assert _stop(capsys) is None


def test_a_briefed_lemon_without_a_waiter_is_blocked(capsys):
    inbox = _briefed()

    blocked = _stop(capsys)

    assert blocked is not None
    assert blocked["decision"] == "block"
    assert inbox.name in blocked["reason"]
    assert "lemonaid inbox watch --self" in blocked["reason"]


def test_an_armed_waiter_lets_the_turn_end(capsys):
    inbox = _briefed()

    with waiter.armed(inbox):
        assert _stop(capsys) is None


def test_a_done_lemon_needs_no_waiter(capsys):
    _briefed(status="done")

    assert _stop(capsys) is None


def test_a_second_stop_is_let_through_so_the_lemon_cannot_loop(capsys):
    _briefed()

    assert _stop(capsys, stop_hook_active=True) is None


def test_a_waiter_that_starts_within_the_grace_period_counts():
    inbox = _briefed()
    release = threading.Event()

    def arm_late() -> None:
        time.sleep(0.2)
        with waiter.armed(inbox):
            release.wait(5)

    thread = threading.Thread(target=arm_late)
    thread.start()
    try:
        assert waiter.is_armed(inbox, grace=2.0)
    finally:
        release.set()
        thread.join()


def test_a_second_waiter_for_the_same_lemon_is_refused():
    inbox = _briefed()

    with (
        waiter.armed(inbox),
        pytest.raises(waiter.AlreadyArmed, match=inbox.name),
        waiter.armed(inbox),
    ):
        pass


def test_inbox_watch_holds_the_lock_until_it_returns(capsys):
    inbox = _briefed()
    parser = argparse.ArgumentParser()
    inbox_parser = parser.add_subparsers().add_parser("inbox")
    cli.add_inbox_parsers(inbox_parser.add_subparsers())
    args = parser.parse_args(
        ["inbox", "watch", "--self", "--channel", "claude:abcd1234", "--timeout", "5"]
    )
    thread = threading.Thread(target=args.func, args=(args,))
    thread.start()
    try:
        assert waiter.is_armed(inbox, grace=2.0)
    finally:
        store.send(inbox, "Wake up.", "codex:sender")
        thread.join()

    assert "Wake up." in capsys.readouterr().out
    assert not waiter.is_armed(inbox)


def test_the_stop_hook_installs_beside_existing_ones(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}})
    )

    install_hooks.install("Stop", install_hooks.WAITER_CHECK_COMMAND, settings)
    install_hooks.install("Stop", install_hooks.WAITER_CHECK_COMMAND, settings)

    commands = [
        hook["command"]
        for entry in json.loads(settings.read_text())["hooks"]["Stop"]
        for hook in entry["hooks"]
    ]
    assert commands == ["mine", install_hooks.WAITER_CHECK_COMMAND]

    install_hooks.uninstall("Stop", install_hooks.WAITER_CHECK_COMMAND, settings)
    assert "waiter-check" not in settings.read_text()


def test_a_brief_check_finds_broken_blocks_the_stop_even_with_a_waiter(capsys):
    inbox = _briefed()
    path = brief_store.briefs_dir() / "lemon.md"
    path.write_text(path.read_text() + "\n## Now\n\n### Done\n\n### Next\n\n- x\n")

    with waiter.armed(inbox):
        blocked = _stop(capsys)

    assert blocked is not None
    assert "brief check" in blocked["reason"]
    assert "`### Done` in ## Now is empty" in blocked["reason"]
    assert "inbox watch" not in blocked["reason"]


def test_pending_handoff_suppresses_only_source_waiter_check(capsys):
    _briefed()
    path = brief_store.briefs_dir() / "lemon.md"
    with db.connect() as conn:
        row = handoff_state.request(
            conn,
            path,
            "claude:abcd1234",
            "codex",
            "work",
            "2",
            "@2",
            "%2",
            "claude",
            time.time() + 600,
        )
        assert not handoff_state.pending_source(conn, path, "claude:another", time.time())

    assert _stop(capsys) is None
    path.write_text(path.read_text() + "\n## Now\n\n### Done\n\n### Next\n\n- x\n")
    blocked = _stop(capsys)
    assert "brief check" in blocked["reason"]
    assert "inbox watch" not in blocked["reason"]

    path.write_text(path.read_text().split("\n## Now")[0] + "\n")
    with db.connect() as conn:
        conn.execute("UPDATE brief_handoffs SET phase = 'failed' WHERE token = ?", (row["token"],))
        conn.commit()
    assert "inbox watch" in _stop(capsys)["reason"]


def test_expired_handoff_restores_waiter_check(capsys):
    _briefed()
    path = brief_store.briefs_dir() / "lemon.md"
    with db.connect() as conn:
        handoff_state.request(
            conn,
            path,
            "claude:abcd1234",
            "codex",
            "work",
            "2",
            "@2",
            "%2",
            "claude",
            time.time() - 1,
        )

    assert "inbox watch" in _stop(capsys)["reason"]


def _parent_with_child(status: str) -> str:
    _briefed()
    with db.connect() as conn:
        [path] = brief_store.briefs_dir().glob("lemon.md")
        parent_id = identity.read(path.read_text())
        path_child = brief_store.briefs_dir() / "child.md"
        path_child.write_text(f"# child\n\nStatus: {status}\n")
        links.set_parent(conn, identity.ensure(conn, path_child), parent_id)
    return parent_id


def test_a_parent_with_a_child_and_no_children_waiter_is_blocked(capsys):
    inbox_lemon = _parent_with_child("working")

    with waiter.armed(store.inbox_for_id(inbox_lemon)):
        blocked = _stop(capsys)

    assert blocked is not None
    assert children_waiter.COMMAND in blocked["reason"]


def test_a_parent_whose_children_are_all_done_still_needs_the_waiter(capsys):
    lemon_id = _parent_with_child("done")

    with waiter.armed(store.inbox_for_id(lemon_id)):
        blocked = _stop(capsys)

    assert blocked is not None
    assert children_waiter.COMMAND in blocked["reason"]


def test_a_running_children_waiter_lets_the_parent_stop(capsys, tmp_path, monkeypatch):
    lemon_id = _parent_with_child("working")
    monkeypatch.setattr(briefs_events, "default_state_dir", lambda: tmp_path)
    stem = briefs_events.state_stem(tmp_path, lemon_id, "", frozenset(briefs_cli.CHILD_TO), False)

    with waiter.armed(store.inbox_for_id(lemon_id)):
        lock = waiter_lock.acquire(stem.with_suffix(".lock"))
        assert lock is not None
        try:
            assert _stop(capsys) is None
        finally:
            lock.close()


def test_a_done_parent_is_not_asked_to_watch_children(capsys):
    lemon_id = _parent_with_child("working")
    assert _stop(capsys) is not None
    path = brief_store.briefs_dir() / "lemon.md"
    path.write_text(path.read_text().replace("Status: working", "Status: done"))
    assert identity.read(path.read_text()) == lemon_id

    assert _stop(capsys) is None


def test_the_reminder_names_the_codex_command_inside_codex(monkeypatch):
    assert "--codex-thread" not in children_waiter.reminder()

    monkeypatch.setenv("CODEX_THREAD_ID", "thread")

    assert "--codex-thread" in children_waiter.reminder()
