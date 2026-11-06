import time

import pytest

from lemonaid.brief import archive
from lemonaid.inbox import db
from lemonaid.messages import recipient

from .shared import DAY, brief, message, session


def _idle_names(days: float = 14) -> list[str]:
    with db.connect() as conn:
        return [i.path.stem for i in archive.idle(conn, days, time.time())]


def test_a_brief_untouched_and_unattached_for_the_window_is_idle():
    brief("old")
    brief("fresh", at=time.time())

    assert _idle_names() == ["old"]


def test_a_live_session_keeps_even_an_old_brief_in_use():
    path, _ = brief("held")
    session(path, "claude:held", live=True)

    assert _idle_names() == []


def test_recent_activity_on_an_archived_session_keeps_it_in_use():
    path, _ = brief("recent")
    session(path, "claude:recent", at=time.time() - DAY)

    assert _idle_names() == []


def test_a_recent_message_in_its_inbox_keeps_it_in_use():
    _, lemon_id = brief("messaged")
    message(lemon_id, time.time() - DAY)

    assert _idle_names() == []


@pytest.mark.parametrize("status", ["blocked", "alert", "merge", "approve", "review", "running"])
def test_a_brief_waiting_on_someone_is_never_idle(status):
    path, _ = brief("waiting", status=status)
    session(path, "codex:waiting")

    assert _idle_names() == []


def test_a_brief_whose_harness_runs_is_never_idle_though_its_inbox_row_is_archived(monkeypatch):
    path, _ = brief("running-harness")
    session(path, "codex:running-harness")
    monkeypatch.setattr(recipient, "harness_alive", lambda row: True)

    assert _idle_names() == []


def test_a_done_brief_whose_harness_has_exited_is_idle(monkeypatch):
    path, _ = brief("exited")
    session(path, "codex:exited")
    monkeypatch.setattr(recipient, "harness_alive", lambda row: False)

    assert _idle_names() == ["exited"]


def test_a_deaf_lemon_whose_harness_runs_is_never_idle(monkeypatch):
    path, _ = brief("deaf")
    session(path, "claude:deaf")
    monkeypatch.setattr(recipient, "harness_alive", lambda row: True)
    monkeypatch.setattr(recipient.waiter, "is_armed", lambda mailbox: False)

    assert _idle_names() == []


def test_a_lemon_with_an_open_inbox_row_is_never_idle_though_its_harness_is_gone(monkeypatch):
    path, _ = brief("open-place")
    session(path, "codex:open-place", live=True)
    monkeypatch.setattr(recipient, "harness_alive", lambda row: False)

    assert _idle_names() == []
