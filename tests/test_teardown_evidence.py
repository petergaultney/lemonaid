from lemonaid.inbox import db, teardown_evidence


def _row():
    with db.connect() as conn:
        return db.add(
            conn,
            channel="claude:lemon",
            message="waiting",
            switch_source="tmux",
            metadata={"tty": "/tty", "tmux_session_order": [1, 1, 1]},
        )


def test_evidence_survives_hook_updates_but_does_not_follow_a_moved_terminal():
    row = _row()
    with db.connect() as conn:
        teardown_evidence.record(conn, [row])
        current = db.add(
            conn,
            channel=row.channel,
            message="stopping",
            switch_source="tmux",
            metadata={"tty": "/tty"},
        )
        assert teardown_evidence.applies(current)
        moved = db.add(
            conn,
            channel=row.channel,
            message="resumed",
            switch_source="tmux",
            metadata={"tty": "/new"},
        )
        assert not teardown_evidence.applies(moved)


def test_archived_session_does_not_resume_with_teardown_evidence():
    row = _row()
    with db.connect() as conn:
        teardown_evidence.record(conn, [row])
        db.archive(conn, row.id)
        resumed = db.add(
            conn,
            channel=row.channel,
            message="resumed",
            switch_source="tmux",
            metadata={"tty": "/tty"},
        )
        assert "place_teardown" not in resumed.metadata


def test_record_does_not_mark_a_row_that_moved_since_capture():
    row = _row()
    with db.connect() as conn:
        moved = db.add(
            conn,
            channel=row.channel,
            message="moved",
            switch_source="tmux",
            metadata={"tty": "/new"},
        )
        teardown_evidence.record(conn, [row])
        assert not teardown_evidence.applies(db.get(conn, moved.id))
