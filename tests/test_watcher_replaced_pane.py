"""A pane replaced by another that got the same tty is archived by its pane id."""

from lemonaid.lemon_watchers import watcher
from lemonaid.tmux import navigation

_TTY = "/dev/ttys120"
_ORDER = (100, 50, 3)
_LIVE = {"ttys120": ["codex"]}


def _row(channel: str) -> tuple:
    return (channel, channel, "/tmp", 0.0, False, _TTY, "message", "tmux")


def _archive(
    live_pane: str, order=_ORDER, pane_ids=None, cached_pane=None, fresh="same"
) -> list[str]:
    archived: list[str] = []
    panes = {None: {_TTY: navigation.PaneLocation("review", "4", order, cached_pane or live_pane)}}
    fresh_panes = (
        None if fresh is None else {_TTY: navigation.PaneLocation("review", "4", order, live_pane)}
    )
    watcher._archive_stale_sessions(
        [_row("codex:old"), _row("codex:new")],
        lambda channel, why: archived.append(channel),
        {},
        panes,
        session_orders={"codex:old": _ORDER, "codex:new": _ORDER},
        tty_processes=_LIVE,
        confirm_panes=lambda _socket: fresh_panes,
        pane_ids=pane_ids or {"codex:old": "%2730", "codex:new": "%2731"},
    )
    return archived


def test_row_recorded_in_a_replaced_pane_is_archived_and_the_live_one_kept():
    assert _archive("%2731") == ["codex:old"]


def test_nothing_is_archived_when_no_pane_ids_were_recorded():
    assert _archive("%2731", pane_ids={"x": "%1"}) == []


def test_a_restarted_server_is_left_to_the_session_order_check():
    assert _archive("%0", order=(100, 99, 3)) == ["codex:old", "codex:new"]


def test_live_row_is_kept_when_only_the_cached_listing_shows_the_old_pane():
    assert "codex:new" not in _archive("%2731", cached_pane="%2730")


def test_nothing_is_archived_on_a_stale_cached_pane_when_tmux_cannot_confirm():
    assert _archive("%2731", cached_pane="%2730", fresh=None) == []
