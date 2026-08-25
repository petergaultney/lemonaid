"""The watcher keeps every tmux-hosted session's location current.

A notification records its own location only when the session notifies, so an
idle one can go days without one - and those are the sessions whose position is
hardest to reconstruct after a crash.
"""

from lemonaid.lemon_watchers import watcher


def _active(channel: str, tty: str | None, switch_source: str | None = "tmux") -> tuple:
    return (channel, "sid", "/tmp", 0.0, False, tty, "message", switch_source)


def _record(active, by_tty, monkeypatch, sockets=None) -> list[tuple]:
    """Run one pass, with `by_tty` standing in for the listing of each server.

    `by_tty` may be a plain dict (one server, whatever socket is asked for) or a
    dict keyed by socket, which is how the cross-server cases are set up.
    """

    def _listing(socket=None):
        if by_tty and all(isinstance(v, dict) for v in by_tty.values()):
            return by_tty.get(socket, {})

        return by_tty

    monkeypatch.setattr(watcher.tmux.navigation, "locations_by_tty", _listing)
    recorded: list[tuple] = []
    watcher._record_locations(active, lambda *args: recorded.append(args), sockets)

    return recorded


def test_records_where_each_session_is(monkeypatch):
    recorded = _record(
        [_active("claude:a", "/dev/ttys001"), _active("claude:b", "/dev/ttys002")],
        {"/dev/ttys001": ("relay", "2"), "/dev/ttys002": ("relay", "3")},
        monkeypatch,
    )

    assert recorded == [("claude:a", "relay", "2", None), ("claude:b", "relay", "3", None)]


def test_records_an_idle_session_that_never_notified(monkeypatch):
    """The whole point: this session is saying nothing, and would be lost."""
    recorded = _record(
        [_active("claude:quiet", "/dev/ttys009")],
        {"/dev/ttys009": ("protostellar/old-work", "2")},
        monkeypatch,
    )

    assert recorded == [("claude:quiet", "protostellar/old-work", "2", None)]


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
        lambda socket=None: (asked.append(socket), {})[1],
    )
    watcher._record_locations([_active("claude:a", None)], lambda *a: None)

    assert not asked


def test_each_session_is_looked_up_on_its_own_server(monkeypatch):
    """Two sessions, two tmux servers. Asking either one about the other's pane
    gets "no such tty", which is why the socket has to pick the server."""
    recorded = _record(
        [_active("claude:a", "/dev/ttys001"), _active("claude:b", "/dev/ttys002")],
        {
            "/tmp/tmux-1/default": {"/dev/ttys001": ("relay", "2")},
            "/tmp/tmux-1/other": {"/dev/ttys002": ("side", "1")},
        },
        monkeypatch,
        sockets={"claude:a": "/tmp/tmux-1/default", "claude:b": "/tmp/tmux-1/other"},
    )

    assert recorded == [
        ("claude:a", "relay", "2", "/tmp/tmux-1/default"),
        ("claude:b", "side", "1", "/tmp/tmux-1/other"),
    ]


def test_one_listing_per_server_not_per_session(monkeypatch):
    """This runs twice a second, so the cost must scale with servers, not rows."""
    asked: list[str | None] = []

    def _listing(socket=None):
        asked.append(socket)
        return {f"/dev/ttys00{i}": ("relay", str(i)) for i in range(1, 5)}

    monkeypatch.setattr(watcher.tmux.navigation, "locations_by_tty", _listing)
    watcher._record_locations(
        [_active(f"claude:{i}", f"/dev/ttys00{i}") for i in range(1, 5)],
        lambda *a: None,
        {f"claude:{i}": "/tmp/tmux-1/default" for i in range(1, 5)},
    )

    assert asked == ["/tmp/tmux-1/default"]
