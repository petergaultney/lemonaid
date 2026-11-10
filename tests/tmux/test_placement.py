"""Where each lost lemon goes back."""

from lemonaid.inbox import db
from lemonaid.tmux import placement


def _row(
    channel: str, session: str, window: str, heard: float, order: list[int] | None = None
) -> db.Notification:
    return db.Notification(
        0,
        channel,
        "",
        metadata={
            "tmux_session": session,
            "tmux_window": window,
            "tmux_session_order": order or [int(heard), 100, 1 if session == "work" else 2],
        },
        created_at=heard,
    )


def _spots(rows, live) -> dict[str, tuple[str, int, bool]]:
    placed, _ = placement.place(rows, live)
    return {row.channel: (s.session, s.index, s.creates_session) for row, s in placed}


def test_lemons_go_back_to_their_recorded_windows_in_new_sessions():
    rows = [_row("a", "work", "1", 10), _row("b", "work", "3", 11), _row("c", "side", "2", 12)]

    assert _spots(rows, {}) == {
        "a": ("work", 1, True),
        "b": ("work", 3, False),
        "c": ("side", 2, True),
    }


def test_the_lemon_heard_from_last_keeps_a_shared_window_and_the_other_gets_the_next():
    rows = [_row("old", "work", "2", 10), _row("new", "work", "2", 20)]

    assert _spots(rows, {}) == {"new": ("work", 2, True), "old": ("work", 3, False)}


def test_a_running_session_keeps_its_windows_and_gains_the_missing_ones():
    rows = [_row("a", "work", "1", 10), _row("b", "work", "2", 11)]

    assert _spots(rows, {"work": {1, 3}}) == {"b": ("work", 2, False), "a": ("work", 4, False)}


def test_a_row_with_no_recorded_window_is_left_out():
    row = db.Notification(0, "x", "", metadata={"tmux_session": "work"})

    assert placement.place([row], {}) == ([], [row])


def _sessions(rows) -> list[str]:
    placed, _ = placement.place(rows, {})
    return list(dict.fromkeys(spot.session for _, spot in placed))


def test_sessions_come_back_in_the_order_tmux_made_them():
    """Not by name: a listing by index or creation should look as it did."""
    rows = [
        _row("a", "alpha", "1", 1, [1700000300, 1700000000, 9]),
        _row("b", "zulu", "1", 2, [1700000100, 1700000000, 2]),
        _row("c", "mike", "1", 3, [1700000200, 1700000000, 5]),
    ]

    assert _sessions(rows) == ["zulu", "mike", "alpha"]


def test_sessions_made_in_the_same_second_are_ordered_by_server_then_id():
    """Ids start again at $0 in each server, so a later server's id can be lower."""
    rows = [
        _row("a", "alpha", "1", 1, [1700000000, 1690000000, 4]),
        _row("b", "zulu", "1", 2, [1700000000, 1690000000, 3]),
        _row("c", "later", "1", 3, [1700000000, 1700000000, 0]),
    ]

    assert _sessions(rows) == ["zulu", "alpha", "later"]


def test_a_session_s_earliest_recorded_order_wins():
    """A lemon whose order was recorded before a later restore still dates the session."""
    rows = [
        _row("a", "alpha", "2", 1, [300, 50, 9]),
        _row("b", "zulu", "1", 2, [200, 50, 2]),
        _row("c", "alpha", "3", 3, [100, 50, 1]),
    ]

    assert _sessions(rows) == ["alpha", "zulu"]


def test_window_zero_is_a_real_index_and_a_garbled_one_is_left_out():
    good, garbled = _row("a", "work", "0", 1), _row("b", "work", "x", 2)

    placed, unplaced = placement.place([good, garbled], {})

    assert [(row.channel, spot.index) for row, spot in placed] == [("a", 0)]
    assert unplaced == [garbled]
