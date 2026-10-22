"""`inbox pin`, `unpin` and `unarchive`, against the temporary test database."""

import argparse
import contextlib
import json

import pytest

from lemonaid.brief import attached
from lemonaid.inbox import db, pin_cli, pins


def _args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(
        **{
            "use_self": False,
            "id": None,
            "channel": None,
            "lemon": None,
            "move": None,
            "json": True,
            **kwargs,
        }
    )


def _session(channel: str, status: str = "read") -> None:
    with db.connect() as conn:
        db.add(conn, channel, "waiting", status=status)


def _run(capsys, command, fails=False, **kwargs) -> dict:
    with pytest.raises(SystemExit) if fails else contextlib.nullcontext():
        command(_args(**kwargs))
    return json.loads(capsys.readouterr().out)


def _pinned() -> list[str]:
    with db.connect() as conn:
        return [n.channel for n in db.get_active(conn) if pins.is_pinned(conn, n.channel)]


def test_pin_is_idempotent_and_unpin_reverses_it(capsys):
    _session("claude:a")

    assert _run(capsys, pin_cli._cmd_pin, channel="claude:a")["newly_pinned"] is True
    assert _run(capsys, pin_cli._cmd_pin, channel="claude:a")["newly_pinned"] is False
    assert _run(capsys, pin_cli._cmd_unpin, channel="claude:a")["unpinned"] is True
    assert _run(capsys, pin_cli._cmd_unpin, channel="claude:a")["unpinned"] is False
    assert _pinned() == []


def test_move_orders_pins_like_the_tui(capsys):
    for name in ("a", "b", "c"):
        _session(f"claude:{name}")
        _run(capsys, pin_cli._cmd_pin, channel=f"claude:{name}")

    _run(capsys, pin_cli._cmd_pin, channel="claude:c", move="up")
    assert _pinned() == ["claude:a", "claude:c", "claude:b"]

    _run(capsys, pin_cli._cmd_pin, channel="claude:b", move="top")
    assert _pinned() == ["claude:b", "claude:a", "claude:c"]

    _run(capsys, pin_cli._cmd_pin, channel="claude:b", move="bottom")
    assert _pinned() == ["claude:a", "claude:c", "claude:b"]

    result = _run(capsys, pin_cli._cmd_pin, fails=True, channel="claude:a", move="up")
    assert "first pin" in result["error"]


def test_pinning_an_archived_session_is_refused(capsys):
    _session("claude:gone", status="archived")

    result = _run(capsys, pin_cli._cmd_pin, fails=True, channel="claude:gone")

    assert "unarchive" in result["error"]
    assert _pinned() == []


def test_unarchive_restores_only_archived_sessions(capsys):
    _session("claude:gone", status="archived")
    _session("claude:here")

    assert _run(capsys, pin_cli._cmd_unarchive, channel="claude:gone")["restored"] is True
    with db.connect() as conn:
        assert db.get_by_channel(conn, "claude:gone", unread_only=False).status == "unread"

    refused = _run(capsys, pin_cli._cmd_unarchive, fails=True, channel="claude:here")
    assert "not archived" in refused["error"]
    missing = _run(capsys, pin_cli._cmd_unarchive, fails=True, channel="claude:nope")
    assert "No inbox session" in missing["error"]


def test_a_brief_attached_to_a_new_channel_takes_the_old_channels_pin(tmp_path):
    brief = tmp_path / "hq.md"
    brief.write_text("# HQ\n")
    _session("claude:old")
    _session("claude:new")
    with db.connect() as conn:
        attached.attach(conn, "claude:old", brief)
        pins.pin(conn, "claude:old")
        attached.attach(conn, "claude:new", brief)

        assert pins.is_pinned(conn, "claude:new")
        assert not pins.is_pinned(conn, "claude:old")
