"""`--self` resolves to a channel only when exactly one live session is recorded at this pane."""

import time

from lemonaid.inbox import db, self_session

HERE = self_session.PaneLocation(tty="/dev/ttys004", session="work", window="2")


def _row(channel: str, upsert: bool = True, **metadata) -> int:
    with db.connect() as conn:
        return db.add(conn, channel, "waiting", metadata=metadata, upsert=upsert).id


def _at(where: self_session.PaneLocation = HERE) -> dict:
    return {"tty": where.tty, "tmux_session": where.session, "tmux_window": where.window}


def _resolve(where: self_session.PaneLocation = HERE) -> tuple[str, str]:
    with db.connect() as conn:
        return self_session.resolve(conn, where)


def test_the_one_session_recorded_at_this_pane_is_chosen():
    _row("claude:mine", **_at())
    _row("claude:elsewhere", **_at(HERE._replace(tty="/dev/ttys009", window="3")))

    assert _resolve() == ("claude:mine", "")


def test_a_reused_tty_in_another_window_does_not_claim_this_pane():
    _row("codex:old-owner", **_at(HERE._replace(session="other", window="1")))
    _row("claude:mine", **_at())

    assert _resolve() == ("claude:mine", "")


def test_a_reused_tty_alone_resolves_nothing():
    _row("codex:old-owner", **_at(HERE._replace(session="other", window="1")))

    channel, error = _resolve()

    assert channel == ""
    assert "lack a matching tmux session and window" in error
    assert "--id or --channel" in error


def test_a_stale_row_of_a_channel_that_has_since_moved_is_ignored():
    _row("claude:moved", **_at())
    time.sleep(0.01)
    _row("claude:moved", upsert=False, **_at(HERE._replace(window="5")))

    channel, error = _resolve()

    assert channel == ""
    assert "No live session" in error


def test_an_archived_session_at_this_pane_is_not_chosen():
    gone = _row("claude:gone", **_at())
    with db.connect() as conn:
        db.archive(conn, gone)

    assert _resolve()[0] == ""


def test_a_snoozed_session_at_this_pane_is_still_live():
    snoozed = _row("claude:snoozed", **_at())
    with db.connect() as conn:
        db.snooze(conn, snoozed, time.time() + 3600)

    assert _resolve() == ("claude:snoozed", "")


def test_two_live_sessions_at_this_pane_are_ambiguous():
    _row("claude:one", **_at())
    _row("codex:two", **_at())

    channel, error = _resolve()

    assert channel == ""
    assert "2 live sessions" in error
    assert "claude:one" in error and "codex:two" in error
    assert "--id or --channel" in error


def test_a_row_missing_its_tmux_location_is_never_matched():
    _row("claude:no-window", tty=HERE.tty, tmux_session=HERE.session)
    _row("claude:tty-only", tty=HERE.tty)

    channel, error = _resolve()

    assert channel == ""
    assert "2 on that tty lack" in error
