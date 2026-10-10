import threading

from lemonaid.inbox import db, presence
from lemonaid.messages import store, waiter

# conftest stubs `Probe.marks` for every test; these exercise the real one.
_MARKS = presence.Probe.marks


def _row(channel: str, tty: str, created_at: float, turn_at: float | None = None):
    return db.Notification(
        1,
        channel,
        "",
        metadata={"tty": f"/dev/{tty}"},
        status="read",
        created_at=created_at,
        turn_at=turn_at,
    )


def _marks(monkeypatch, rows, ttys, now=1000.0):
    monkeypatch.setattr(presence, "_harness_ttys", lambda: ttys)
    lemon_ids = {row.channel: f"lemon-{i}.QuickOdd" for i, row in enumerate(rows)}
    return _MARKS(presence.Probe(), rows, lemon_ids, now)


def test_an_idle_claude_lemon_without_an_inbox_waiter_is_deaf(monkeypatch):
    row = _row("claude:a", "ttys001", created_at=10.0)

    assert _marks(monkeypatch, [row], frozenset({"ttys001"})) == {"claude:a": "deaf"}


def test_an_idle_claude_lemon_with_its_inbox_waiter_armed_is_unmarked(monkeypatch):
    row = _row("claude:a", "ttys001", created_at=10.0)
    armed, release = threading.Event(), threading.Event()

    def hold():
        with waiter.armed(store.inbox_for_id("lemon-0.QuickOdd")):
            armed.set()
            release.wait()

    holder = threading.Thread(target=hold)
    holder.start()
    armed.wait()
    try:
        assert _marks(monkeypatch, [row], frozenset({"ttys001"})) == {}
    finally:
        release.set()
        holder.join()


def test_a_lemon_whose_terminal_runs_no_harness_is_dead(monkeypatch):
    rows = [_row("claude:a", "ttys001", created_at=10.0), _row("codex:b", "ttys002", 10.0)]

    assert _marks(monkeypatch, rows, frozenset()) == {"claude:a": "dead", "codex:b": "dead"}


def test_a_codex_lemon_with_a_harness_always_listens(monkeypatch):
    row = _row("codex:b", "ttys002", created_at=10.0)

    assert _marks(monkeypatch, [row], frozenset({"ttys002"})) == {}


def test_a_row_reported_after_the_listing_is_not_marked_dead(monkeypatch):
    row = _row("codex:b", "ttys002", created_at=2000.0)

    assert _marks(monkeypatch, [row], frozenset(), now=1000.0) == {}


def test_a_mid_turn_claude_lemon_is_not_deaf(monkeypatch):
    row = _row("claude:a", "ttys001", created_at=10.0, turn_at=995.0)

    assert _marks(monkeypatch, [row], frozenset({"ttys001"})) == {}


def test_rows_without_a_lemon_id_are_skipped(monkeypatch):
    monkeypatch.setattr(presence, "_harness_ttys", lambda: frozenset())

    assert _MARKS(presence.Probe(), [_row("claude:a", "ttys001", 10.0)], {}, 1000.0) == {}


def test_a_lemon_whose_inbox_cannot_be_checked_is_unmarked(monkeypatch):
    monkeypatch.setattr(presence, "_harness_ttys", lambda: frozenset({"ttys001"}))
    row = _row("claude:a", "ttys001", 10.0)

    assert _MARKS(presence.Probe(), [row], {"claude:a": "../bad"}, 1000.0) == {}


def test_deaf_waits_until_it_has_lasted(monkeypatch):
    monkeypatch.setattr(presence, "_harness_ttys", lambda: frozenset({"ttys001"}))
    row = _row("claude:a", "ttys001", 10.0)
    probe = presence.Probe(deaf_after=15.0)
    ids = {"claude:a": "lemon-a.QuickOdd"}

    assert _MARKS(probe, [row], ids, 1000.0) == {}
    assert _MARKS(probe, [row], ids, 1014.0) == {}
    assert _MARKS(probe, [row], ids, 1015.0) == {"claude:a": "deaf"}
