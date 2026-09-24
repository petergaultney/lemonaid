"""The TUI key and the CLI resolve a session to the same directories and names."""

from pathlib import Path

import pytest

from lemonaid.brief import session, target
from lemonaid.inbox import db

_SESSION_DIRS = {"hq": Path("/work/engineering-infra"), "pair": Path("/work/pair")}


@pytest.fixture(autouse=True)
def _fake_tmux(monkeypatch):
    monkeypatch.setattr(session, "session_dir", _SESSION_DIRS.get)
    monkeypatch.setattr(session, "lemon_name", lambda s: "")


def _row(channel: str, tmux_session: str, cwd: str, created_at: float = 0) -> db.Notification:
    return db.Notification(
        id=1,
        channel=channel,
        message="",
        name=f"{channel} card",
        metadata={"tmux_session": tmux_session, "cwd": cwd},
        created_at=created_at,
    )


def test_a_card_searches_its_lemons_cwd_then_its_sessions_directory():
    found = target.for_notification(_row("claude:abc", "hq", "/work/ds-monorepo"))

    assert found.dirs == [Path("/work/ds-monorepo"), Path("/work/engineering-infra")]


def test_the_cli_finds_the_same_directories_as_the_card():
    row = _row("claude:abc", "hq", "/work/ds-monorepo")

    assert target.for_session("hq", [row]) == target.for_notification(row)


def test_a_codex_card_prefers_the_codex_brief_over_the_session_name():
    found = target.for_notification(_row("codex:t1", "hq", "/work/ds-monorepo"))

    assert found.names[:2] == ["codex", "hq"]


def test_a_session_with_two_lemons_names_neither_backend():
    rows = [
        _row("claude:a", "pair", "/work/pair", created_at=1),
        _row("codex:b", "pair", "/work/pair/sub", created_at=2),
    ]

    found = target.for_session("pair", rows)

    assert found.names == ["pair"]
    assert found.dirs == [Path("/work/pair/sub"), Path("/work/pair")]


def test_a_session_the_inbox_never_saw_still_has_its_tmux_directory():
    assert target.for_session("hq", []).dirs == [Path("/work/engineering-infra")]
