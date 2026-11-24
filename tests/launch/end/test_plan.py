"""Which lemons `lemon end` ends: one whose brief has a Status its caller expects."""

import pytest

from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.launch.end import closing, done, plan
from lemonaid.launch.restart import planning

from ..restart import runtime_fixture
from . import shared


def _build(target: str, expected: tuple[str, ...] = ("done",)) -> dict:
    with db.connect() as conn:
        return plan.build(conn, target, Config(), expected)


def _owned(monkeypatch) -> None:
    fixed = runtime_fixture.shared
    owned = planning.Owned(fixed.TARGET, fixed.SOURCE, fixed.ROOT, [fixed.SOURCE, fixed.ROOT])
    monkeypatch.setattr(plan, "_harness", lambda row: owned)
    monkeypatch.setattr(closing, "preview", lambda pane, protected: "close its pane")


def test_it_ends_a_lemon_whose_status_is_one_its_caller_expects(monkeypatch):
    reviewer, _ = shared.lemon("reviewer", "approve", channel="codex:reviewer")
    _owned(monkeypatch)
    with db.connect() as conn:
        conn.execute("UPDATE notifications SET turn_at = 123 WHERE channel = 'codex:reviewer'")
        conn.commit()

    with pytest.raises(ValueError, match=f"^{reviewer}'s Status is approve, not done$"):
        _build(reviewer)
    with pytest.raises(ValueError, match=r"Status is approve, not done or merge$"):
        _build(reviewer, ("done", "merge"))
    planned = _build(reviewer, ("done", "Approve"))

    assert (planned["expected"], planned["by"]) == (["done", "Approve"], "user")
    assert planned["closing"] == "close its pane"


def test_none_is_what_a_brief_with_no_status_has():
    worker, _ = shared.lemon("worker")

    with pytest.raises(ValueError, match=r"Status is none, not done$"):
        _build(worker)
    planned = _build(worker, ("none",))

    assert (planned["source"], planned["card"], planned["channel"]) == (None, False, "")
    assert planned["closing"] == "leave its pane as it is: its harness has already exited"


def test_a_lemon_alone_in_its_session_is_its_places_lemon():
    shared.lemon("author", channel="claude:author", session="s-author")
    shared.lemon("reviewer", channel="codex:reviewer", session="s-author")
    shared.lemon("loner", channel="claude:loner", session="s-loner")
    shared.lemon("snoozer", channel="claude:snoozer", session="s-snoozer")
    shared.lemon("sleepy", channel="codex:sleepy", session="s-snoozer")
    with db.connect() as conn:
        conn.execute("UPDATE notifications SET status = 'snoozed' WHERE channel = 'codex:sleepy'")
        conn.commit()
        rows = {
            channel: db.get_by_channel(conn, channel, unread_only=False)
            for channel in ("codex:reviewer", "claude:loner", "claude:snoozer", "claude:author")
        }

        assert done.sole_session(conn, rows["codex:reviewer"]) == ""
        assert done.sole_session(conn, rows["claude:loner"]) == "s-loner"
        assert done.sole_session(conn, rows["claude:snoozer"]) == ""
        assert done.sole_session(conn, None) == ""
    shared.archive_card("codex:reviewer")
    with db.connect() as conn:
        assert done.sole_session(conn, rows["claude:author"]) == "s-author"
