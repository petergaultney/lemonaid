"""`brief show SESSION --popup` from a key binding shows the lemon in the pressed window."""

import pytest

from lemonaid.brief import attached, cli, session
from lemonaid.inbox import db


@pytest.fixture
def hq(monkeypatch, tmp_path):
    """Session `hq`: a lemon with a brief in window 1 and one without in window 3,
    with the client looking at window 3 from a binding's `run-shell` (no TMUX_PANE)."""
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setattr(session, "session_dir", lambda s: tmp_path)
    monkeypatch.setattr(session, "lemon_name", lambda s: "")
    monkeypatch.setattr(
        session,
        "_tmux",
        lambda *args: "hq\t3" if args[:2] == ("display-message", "-p") else "",
    )
    brief = tmp_path / "control-center.md"
    brief.write_text("# HQ\n\nStatus: blocked\n")
    with db.connect() as conn:
        db.add(conn, "claude:hq", "", "HQ", {"tmux_session": "hq", "tmux_window": 1, "cwd": "/"})
        db.add(conn, "claude:vault", "", "Vault", {"tmux_session": "hq", "tmux_window": 3})
        attached.attach(conn, "claude:hq", brief)
    return brief


def test_a_session_only_popup_shows_the_lemon_in_the_clients_window(hq):
    found = cli._target("hq", [], [], "", [], "", popup=True)

    assert found.attached == []
    assert found.lemon is not None and found.lemon.name == "Vault"


def test_naming_the_window_still_wins(hq):
    found = cli._target("hq:1", [], [], "", [], "", popup=True)

    assert found.attached == [hq]


def test_printing_a_session_still_shows_every_lemon_in_it(hq):
    found = cli._target("hq", [], [], "", [], "")

    assert found.attached == [hq]
    assert [member.lemon.name for member in found.members if member.lemon] == ["Vault", "HQ"]


def test_a_client_in_another_session_gets_the_whole_session(hq, monkeypatch):
    monkeypatch.setattr(session, "_tmux", lambda *args: "elsewhere\t3")

    assert cli._target("hq", [], [], "", [], "", popup=True).attached == [hq]


def test_outside_tmux_there_is_no_client_window(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(session, "_tmux", lambda *args: "hq\t3")

    assert session.client_window("hq") == ""


def test_a_pane_asks_about_itself(monkeypatch):
    monkeypatch.setenv("TMUX_PANE", "%7")
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(session, "_tmux", lambda *args: calls.append(args) or "hq\t2")

    assert session.client_window("hq") == "2"
    assert calls[0][:4] == ("display-message", "-p", "-t", "%7")
