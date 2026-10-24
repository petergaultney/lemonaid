"""`lemonaid restore relink`: rows follow the lemon's own process, never a bare tty."""

from lemonaid.inbox import db
from lemonaid.tmux import relink

_HQ_PANE = {
    "tty": "/dev/ttys001",
    "tmux_session": "hq",
    "tmux_window": "1",
    "tmux_pane_identity": ["%0", 900],
    "tmux_session_order": [1000, 900, 0],
}
_REVIEW_PANE = {**_HQ_PANE, "tty": "/dev/ttys063", "tmux_session": "ua", "tmux_window": "4"}
_PANES = {"/dev/ttys001": [_HQ_PANE], "/dev/ttys063": [_REVIEW_PANE]}


def _row(channel: str, **metadata) -> db.Notification:
    with db.connect() as conn:
        return db.add(conn, channel, "waiting", metadata=metadata, switch_source="tmux")


def _states(rows, owners) -> dict[str, str]:
    return {r.row.channel: r.state for r in relink.plan(rows, owners, _PANES)}


def test_a_row_on_a_dead_server_s_tty_follows_its_session_to_its_new_pane():
    hq = _row("claude:b7396389", session_id="b7396389-full", tty="/dev/ttys021", tmux_session="hq")

    [result] = relink.plan([hq], {"b7396389-full": {"/dev/ttys001"}}, _PANES)

    assert (result.state, result.location) == (relink.RELINKED, _HQ_PANE)


def test_a_row_already_on_its_lemon_s_pane_is_left_alone():
    hq = _row("claude:b7396389", session_id="b7396389-full", **_HQ_PANE)

    assert _states([hq], {"b7396389-full": {"/dev/ttys001"}}) == {"claude:b7396389": relink.OK}


def test_a_lemon_that_is_not_running_keeps_its_row_unless_its_pane_is_another_lemon_s():
    gone = _row("codex:gone", tty="/dev/ttys099", tmux_session="x", tmux_window="0")
    crowded = _row("codex:crowded", tty="/dev/ttys063", tmux_session="x", tmux_window="0")

    assert _states([gone, crowded], {"review": {"/dev/ttys063"}}) == {
        "codex:gone": relink.NOT_RUNNING,
        "codex:crowded": relink.FORGOTTEN,
    }


def test_a_lemon_in_no_tmux_pane_is_not_guessed_at():
    row = _row("codex:t1", tty="/dev/ttys021")

    assert _states([row], {"t1": {"/dev/ttys777"}}) == {"codex:t1": relink.UNPLACEABLE}


def test_applying_twice_changes_nothing_the_second_time():
    _row("claude:b7396389", session_id="b7396389-full", tty="/dev/ttys021", tmux_session="hq")
    _row("codex:crowded", tty="/dev/ttys063", tmux_session="x", tmux_window="0")
    owners = {"b7396389-full": {"/dev/ttys001"}, "review": {"/dev/ttys063"}}

    def run() -> list[relink.Relink]:
        with db.connect() as conn:
            return relink.apply(conn, relink.plan(db.get_active(conn), owners, _PANES))

    assert {r.row.channel for r in run()} == {"claude:b7396389", "codex:crowded"}
    assert run() == []
    with db.connect() as conn:
        rows = {n.channel: n.metadata for n in db.get_active(conn)}
    assert rows["claude:b7396389"]["tty"] == "/dev/ttys001"
    assert "tty" not in rows["codex:crowded"]
