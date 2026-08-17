"""The watcher keeps every tmux-hosted session's location current.

A notification records its own location only when the session notifies, so an
idle one can go days without one - and those are the sessions whose position is
hardest to reconstruct after a crash.
"""

from lemonaid.lemon_watchers import watcher


def _active(channel: str, tty: str | None, switch_source: str | None = "tmux") -> tuple:
    return (channel, "sid", "/tmp", 0.0, False, tty, "message", switch_source)


def _record(active, by_tty, monkeypatch) -> list[tuple[str, str, str]]:
    monkeypatch.setattr(watcher.tmux.navigation, "locations_by_tty", lambda: by_tty)
    recorded: list[tuple[str, str, str]] = []
    watcher._record_locations(active, lambda *args: recorded.append(args))

    return recorded


def test_records_where_each_session_is(monkeypatch):
    recorded = _record(
        [_active("claude:a", "/dev/ttys001"), _active("claude:b", "/dev/ttys002")],
        {"/dev/ttys001": ("relay", "2"), "/dev/ttys002": ("relay", "3")},
        monkeypatch,
    )

    assert recorded == [("claude:a", "relay", "2"), ("claude:b", "relay", "3")]


def test_records_an_idle_session_that_never_notified(monkeypatch):
    """The whole point: this session is saying nothing, and would be lost."""
    recorded = _record(
        [_active("claude:quiet", "/dev/ttys009")],
        {"/dev/ttys009": ("protostellar/old-work", "2")},
        monkeypatch,
    )

    assert recorded == [("claude:quiet", "protostellar/old-work", "2")]


def test_skips_a_session_with_no_tty(monkeypatch):
    assert _record([_active("claude:a", None)], {"/dev/ttys001": ("relay", "2")}, monkeypatch) == []


def test_skips_a_session_that_is_not_in_tmux(monkeypatch):
    active = [_active("claude:a", "/dev/ttys001", switch_source="wezterm")]

    assert _record(active, {"/dev/ttys001": ("relay", "2")}, monkeypatch) == []


def test_skips_a_tty_tmux_does_not_know(monkeypatch):
    """The pane is gone; archiving handles that, and inventing a location would not."""
    assert _record([_active("claude:a", "/dev/ttys404")], {}, monkeypatch) == []


def test_does_not_ask_tmux_when_nothing_could_match(monkeypatch):
    """This runs on every poll, so the common idle case must cost nothing."""
    asked = []
    monkeypatch.setattr(
        watcher.tmux.navigation,
        "locations_by_tty",
        lambda: (asked.append(1), {})[1],
    )
    watcher._record_locations([_active("claude:a", None)], lambda *a: None)

    assert not asked
