"""`brief attach` refuses a brief another running session holds."""

import pytest

from lemonaid.brief import attached, session
from lemonaid.inbox import db
from lemonaid.messages import recipient

from .test_brief_attached import _attached_to, _brief, _lemon, _run


@pytest.fixture(autouse=True)
def _fake_tmux(monkeypatch, tmp_path):
    monkeypatch.setattr(session, "session_dir", lambda s: tmp_path / "place")
    monkeypatch.setattr(session, "lemon_name", lambda s: "")


def _hold(monkeypatch, *, alive: bool) -> None:
    _lemon("codex:old", "work", "2", 1)
    _lemon("codex:new", "work", "4", 2)

    with db.connect() as conn:
        attached.attach(conn, "codex:old", _brief("hq"))
    monkeypatch.setattr(recipient, "harness_alive", lambda row: alive)


def test_a_running_holder_is_not_displaced(capsys, monkeypatch):
    _hold(monkeypatch, alive=True)

    out = _run(capsys, "attach", "--channel", "codex:new", str(_brief("hq")))

    assert "held by codex:old" in out["error"]
    assert "--force" in out["error"]
    assert _attached_to("codex:old") == _brief("hq")
    assert _attached_to("codex:new") is None


def test_force_takes_it_from_a_running_holder(capsys, monkeypatch):
    _hold(monkeypatch, alive=True)

    out = _run(capsys, "attach", "--force", "--channel", "codex:new", str(_brief("hq")))

    assert out["moved_from"] == "codex:old"
    assert _attached_to("codex:new") == _brief("hq")


def test_a_dead_holder_is_replaced_without_force(capsys, monkeypatch):
    _hold(monkeypatch, alive=False)

    out = _run(capsys, "attach", "--channel", "codex:new", str(_brief("hq")))

    assert out["error"] is None
    assert _attached_to("codex:new") == _brief("hq")


def test_reattaching_to_the_same_channel_is_not_refused(capsys, monkeypatch):
    _hold(monkeypatch, alive=True)

    out = _run(capsys, "attach", "--channel", "codex:old", str(_brief("hq")))

    assert out["error"] is None


def test_an_unheld_brief_attaches(capsys, monkeypatch):
    _hold(monkeypatch, alive=True)

    out = _run(capsys, "attach", "--channel", "codex:new", str(_brief("other")))

    assert out["error"] is None


def test_a_deaf_holder_is_still_refused(capsys, monkeypatch):
    _lemon("claude:old", "work", "2", 1)
    _lemon("codex:new", "work", "4", 2)
    with db.connect() as conn:
        attached.attach(conn, "claude:old", _brief("hq"))
    monkeypatch.setattr(recipient, "harness_alive", lambda row: True)

    out = _run(capsys, "attach", "--channel", "codex:new", str(_brief("hq")))

    assert "claude:old, which is deaf" in out["error"]
