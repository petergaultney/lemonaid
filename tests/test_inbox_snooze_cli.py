"""`inbox snooze`: a lemon snoozes its own row, by the TUI picker's syntax."""

import argparse
import contextlib
import json
import time
from datetime import datetime

import pytest

from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db, self_session, snooze_cli, snooze_time

HERE = self_session.PaneLocation(tty="/dev/ttys004", session="work", window="2")


def _args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(
        **{
            "use_self": False,
            "id": None,
            "channel": None,
            "lemon": None,
            "when": "",
            "clear": False,
            "json": True,
            **kwargs,
        }
    )


def _session(channel: str, where: self_session.PaneLocation = HERE, status="read") -> int:
    metadata = {"tty": where.tty, "tmux_session": where.session, "tmux_window": where.window}
    with db.connect() as conn:
        return db.add(conn, channel, "waiting", metadata=metadata, status=status).id


def _run(monkeypatch, capsys, fails=False, **kwargs) -> dict:
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(self_session, "pane_location", lambda _pane: HERE)
    with pytest.raises(SystemExit) if fails else contextlib.nullcontext():
        snooze_cli._cmd_snooze(_args(**kwargs))
    return json.loads(capsys.readouterr().out)


def _row(notification_id: int) -> db.Notification:
    with db.connect() as conn:
        found = db.get(conn, notification_id)
    assert found is not None
    return found


def test_self_snoozes_the_calling_lemon_through_its_turn_end(monkeypatch, capsys):
    mine = _session("claude:mine")
    other = _session("claude:other", HERE._replace(window="3"))
    before = time.time()

    result = _run(monkeypatch, capsys, use_self=True, when="2h")

    assert result["channel"] == "claude:mine"
    assert result["error"] is None
    assert before + 7200 <= result["snooze_until"] <= time.time() + 7200
    assert result["wakes"] == datetime.fromtimestamp(result["snooze_until"]).isoformat(
        timespec="minutes"
    )
    assert _row(other).status == "read"

    with db.connect() as conn:
        db.add(conn, "claude:mine", "turn ended", ends_turn=True)
    assert _row(mine).is_snoozed


def test_morning_matches_the_tui_picker(monkeypatch, capsys):
    mine = _session("claude:mine")

    result = _run(monkeypatch, capsys, use_self=True, when="morning")

    assert result["snooze_until"] == pytest.approx(
        snooze_time.next_morning(time.time(), snooze_time.DEFAULT_DAY_START), abs=5
    )
    assert _row(mine).snooze_until == result["snooze_until"]


def test_clear_wakes_the_row_and_is_idempotent(monkeypatch, capsys):
    mine = _session("claude:mine")
    _run(monkeypatch, capsys, use_self=True, when="45")

    assert _run(monkeypatch, capsys, use_self=True, clear=True)["woke"] is True
    assert _row(mine).status == "read"
    assert _run(monkeypatch, capsys, use_self=True, clear=True)["woke"] is False


@pytest.mark.parametrize("when", ["soon", "inf", "1e300d"])
def test_refuses_a_bad_duration_without_snoozing(monkeypatch, capsys, when):
    mine = _session("claude:mine")

    result = _run(monkeypatch, capsys, fails=True, use_self=True, when=when)

    assert "45m" in result["error"]
    assert result["snooze_until"] is None
    assert _row(mine).status == "read"


def test_refuses_an_archived_session(monkeypatch, capsys):
    mine = _session("claude:gone")
    with db.connect() as conn:
        db.archive(conn, mine)

    result = _run(monkeypatch, capsys, fails=True, channel="claude:gone", when="1h")

    assert "archived" in result["error"]
    assert _row(mine).is_archived


def test_lemon_names_the_session_by_its_brief(monkeypatch, capsys):
    mine = _session("claude:mine")
    path = brief_store.briefs_dir() / "views.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# views\n")
    with db.connect() as conn:
        attached.attach(conn, "claude:mine", path)

    result = _run(monkeypatch, capsys, lemon="views", when="1h")

    assert result["channel"] == "claude:mine"
    assert _row(mine).is_snoozed


def test_plain_output_says_when_it_wakes(monkeypatch, capsys):
    _session("claude:mine")
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(self_session, "pane_location", lambda _pane: HERE)

    snooze_cli._cmd_snooze(_args(use_self=True, when="1h", json=False))

    assert capsys.readouterr().out.startswith("Snoozed claude:mine until ")
