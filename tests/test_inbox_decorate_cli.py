"""`inbox rename` / `inbox emoji` / `inbox emojis`: every target becomes one channel."""

import argparse
import contextlib
import json
import time

import pytest

from lemonaid.inbox import db, decorate_cli, emoji, self_session

HERE = self_session.PaneLocation(tty="/dev/ttys004", session="work", window="2")


def _args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(
        **{
            "use_self": False,
            "id": None,
            "channel": None,
            "name": "",
            "emoji": "",
            "clear": False,
            "json": True,
            **kwargs,
        }
    )


def _session(channel: str, name: str, where: self_session.PaneLocation = HERE) -> int:
    metadata = {"tty": where.tty, "tmux_session": where.session, "tmux_window": where.window}
    with db.connect() as conn:
        return db.add(conn, channel, "waiting", name=name, metadata=metadata).id


def _run(monkeypatch, capsys, command, where=HERE, fails=False, **kwargs) -> dict:
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(self_session, "pane_location", lambda _pane: where)
    with pytest.raises(SystemExit) if fails else contextlib.nullcontext():
        command(_args(**kwargs))
    return json.loads(capsys.readouterr().out)


def _name(channel: str) -> str | None:
    with db.connect() as conn:
        found = db.get_by_channel(conn, channel, unread_only=False)
    return found.name if found else None


def _stored() -> dict[str, str]:
    with db.connect() as conn:
        return emoji.by_channel(conn)


def test_self_renames_the_session_recorded_at_this_pane(monkeypatch, capsys):
    _session("claude:mine", "auto title")
    _session("claude:other", "elsewhere", HERE._replace(window="3"))

    result = _run(monkeypatch, capsys, decorate_cli._cmd_rename, use_self=True, name="views")

    assert result == {"channel": "claude:mine", "name": "views", "error": None}
    assert _name("claude:other") == "elsewhere"


def test_clear_restores_the_backend_name(monkeypatch, capsys):
    _session("claude:mine", "auto title")
    _run(monkeypatch, capsys, decorate_cli._cmd_rename, use_self=True, name="views")

    _run(monkeypatch, capsys, decorate_cli._cmd_rename, use_self=True, clear=True)

    assert _name("claude:mine") == "auto title"


def test_an_id_renames_its_channels_newest_row(monkeypatch, capsys):
    first = _session("claude:mine", "auto title")
    time.sleep(0.01)
    with db.connect() as conn:
        db.add(conn, "claude:mine", "again", name="auto title", upsert=False)

    result = _run(monkeypatch, capsys, decorate_cli._cmd_rename, id=first, name="views")

    assert result["channel"] == "claude:mine"
    assert _name("claude:mine") == "views"


def test_an_ambiguous_self_changes_nothing(monkeypatch, capsys):
    _session("claude:one", "one")
    _session("codex:two", "two")

    result = _run(
        monkeypatch, capsys, decorate_cli._cmd_emoji, use_self=True, emoji="🦫", fails=True
    )

    assert "--id or --channel" in result["error"]
    assert _stored() == {}


def test_an_explicit_channel_works_where_self_would_be_ambiguous(monkeypatch, capsys):
    _session("claude:one", "one")
    _session("codex:two", "two")

    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, channel="codex:two", emoji="🦫")

    assert _stored() == {"codex:two": "🦫"}


def test_an_unknown_channel_is_an_error(monkeypatch, capsys):
    result = _run(
        monkeypatch, capsys, decorate_cli._cmd_emoji, channel="claude:nope", emoji="🦫", fails=True
    )

    assert "No inbox session" in result["error"]


def test_self_sets_replaces_and_clears_the_calling_lemons_emoji(monkeypatch, capsys):
    _session("claude:mine", "mine")
    _session("codex:neighbour", "neighbour", HERE._replace(window="3"))

    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, use_self=True, emoji="🦫")
    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, channel="codex:neighbour", emoji="🧪")
    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, use_self=True, emoji="🌵")
    assert _stored() == {"claude:mine": "🌵", "codex:neighbour": "🧪"}

    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, use_self=True, clear=True)
    assert _stored() == {"codex:neighbour": "🧪"}


def test_any_nonempty_value_is_accepted(monkeypatch, capsys):
    _session("claude:mine", "mine")

    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, use_self=True, emoji="🦫🦫")

    assert _stored() == {"claude:mine": "🦫🦫"}


def test_an_emoji_another_live_session_holds_is_refused(monkeypatch, capsys):
    _session("claude:mine", "mine")
    _session("codex:theirs", "theirs", HERE._replace(window="3"))
    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, channel="codex:theirs", emoji="❤️")

    refused = _run(
        monkeypatch, capsys, decorate_cli._cmd_emoji, use_self=True, emoji="❤", fails=True
    )

    assert "held by live session codex:theirs" in refused["error"]
    assert _stored() == {"codex:theirs": "❤️"}


def test_a_snoozed_sessions_emoji_is_still_held(monkeypatch, capsys):
    _session("claude:mine", "mine")
    snoozed = _session("codex:snoozed", "snoozed", HERE._replace(window="3"))
    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, channel="codex:snoozed", emoji="🦫")
    with db.connect() as conn:
        db.snooze(conn, snoozed, time.time() + 3600)

    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, use_self=True, emoji="🦫", fails=True)

    assert "claude:mine" not in _stored()


def test_an_archived_session_keeps_its_emoji_but_releases_it(monkeypatch, capsys):
    _session("claude:mine", "mine")
    gone = _session("codex:gone", "gone", HERE._replace(window="3"))
    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, channel="codex:gone", emoji="🦫")
    with db.connect() as conn:
        db.archive(conn, gone)

    _run(monkeypatch, capsys, decorate_cli._cmd_emoji, use_self=True, emoji="🦫")

    assert _stored() == {"codex:gone": "🦫", "claude:mine": "🦫"}


def test_emojis_lists_only_live_holders(capsys):
    _session("claude:live", "live one")
    gone = _session("codex:gone", "gone", HERE._replace(window="3"))
    with db.connect() as conn:
        emoji.set_emoji(conn, "claude:live", "🦫")
        emoji.set_emoji(conn, "codex:gone", "🧪")
        db.archive(conn, gone)

    decorate_cli._cmd_emojis(argparse.Namespace(json=True))

    held = json.loads(capsys.readouterr().out)
    assert [(h["emoji"], h["channel"], h["name"]) for h in held] == [
        ("🦫", "claude:live", "live one")
    ]
