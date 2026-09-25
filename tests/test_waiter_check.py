"""A Claude lemon with a brief cannot end its turn until its inbox waiter holds the lock."""

import argparse
import json
import threading
import time
from pathlib import Path

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.claude import install_hooks, waiter_check
from lemonaid.inbox import db
from lemonaid.messages import cli, store, waiter

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

    with waiter.armed(inbox), pytest.raises(waiter.AlreadyArmed, match=inbox.name):
        with waiter.armed(inbox):
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
