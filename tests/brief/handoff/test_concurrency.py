"""Concurrent coordinators must reserve only one target pane per token."""

import threading
import time

from lemonaid.brief import handoff_coordinator, handoff_launch, handoff_state, handoff_tmux
from lemonaid.inbox import db

from .shared import requested


def test_concurrent_advance_opens_only_one_pane(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    monkeypatch.setattr(db, "get_db_path", lambda: path.parent / "inbox.db")
    monkeypatch.setattr(handoff_state, "ready", lambda *_: (True, ""))
    monkeypatch.setattr(handoff_tmux, "has_pane", lambda *_: True)

    opened = []
    opening = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    errors = []

    def launch(other_conn, handoff):
        opened.append(handoff["token"])
        if len(opened) == 1:
            opening.set()
            if not release.wait(3):
                raise TimeoutError("first launch was not released")

        other_conn.execute(
            """UPDATE brief_handoffs SET phase = 'launched', target_window = '2',
               target_window_id = '@2', target_pane_id = '%3' WHERE token = ?""",
            (handoff["token"],),
        )
        other_conn.commit()

    monkeypatch.setattr(handoff_launch, "run", launch)

    def advance(started=None):
        try:
            with db.connect(path.parent / "inbox.db") as other_conn:
                if started:
                    started.set()
                handoff_coordinator.advance(other_conn, row["token"])
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=advance)
    second = threading.Thread(target=advance, args=(second_started,))
    first.start()
    try:
        assert opening.wait(3)
        second.start()
        assert second_started.wait(3)
        time.sleep(0.2)
        assert opened == [row["token"]]
    finally:
        release.set()
        first.join(3)
        if second.ident:
            second.join(3)

    assert not first.is_alive() and not second.is_alive()
    assert not errors
    assert opened == [row["token"]]
