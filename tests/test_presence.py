import dataclasses
import threading

from lemonaid.brief import attached, identity
from lemonaid.inbox import db, presence
from lemonaid.inbox.tui.rows import brief_cards
from lemonaid.inbox.view import ordered_active
from lemonaid.messages import recipient, store, waiter

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
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["fish"])
    rows = [_row("claude:a", "ttys001", created_at=10.0), _row("codex:b", "ttys002", 10.0)]

    assert _marks(monkeypatch, rows, frozenset()) == {"claude:a": "dead", "codex:b": "dead"}


def test_a_batch_miss_is_confirmed_with_the_doctor_probe(monkeypatch):
    row = _row("codex:b", "ttys002", created_at=10.0)
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["fish", "/opt/bin/codex"])

    assert _marks(monkeypatch, [row], frozenset()) == {"codex:b": "deaf"}


def test_an_uncheckable_batch_miss_is_not_dead(monkeypatch):
    row = _row("codex:b", "ttys002", created_at=10.0)
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: None)

    assert _marks(monkeypatch, [row], frozenset()) == {"codex:b": "deaf"}


def test_confirmations_are_cached_until_the_listing_refreshes(monkeypatch):
    monkeypatch.setattr(presence, "_harness_ttys", lambda: frozenset())
    calls = []
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: calls.append(tty) or ["codex"])
    row = _row("codex:b", "ttys002", created_at=10.0)
    probe = presence.Probe()
    ids = {row.channel: "lemon-b.QuickOdd"}

    assert _MARKS(probe, [row], ids, 1000.0) == {row.channel: "deaf"}
    assert _MARKS(probe, [row], ids, 1001.0) == {row.channel: "deaf"}
    assert len(calls) == 1
    assert _MARKS(probe, [row], ids, 1010.0) == {row.channel: "deaf"}
    assert len(calls) == 2


def test_cmux_uses_its_current_session_instead_of_the_recorded_tty(monkeypatch):
    row = dataclasses.replace(_row("codex:b", "ttys002", 10.0), switch_source="cmux")
    monkeypatch.setattr(
        recipient.handlers, "where_sessions_are", lambda sessions, fresh: {row.channel: "ttys003"}
    )

    assert _marks(monkeypatch, [row], frozenset()) == {row.channel: "deaf"}


def test_moving_a_watched_doc_does_not_make_the_card_dead(monkeypatch, tmp_path):
    monkeypatch.setattr(presence.Probe, "marks", _MARKS)
    monkeypatch.setattr(presence, "_harness_ttys", lambda: frozenset())
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["codex"])
    doc = tmp_path / "design.md"
    doc.write_text("# Design\n")
    brief = tmp_path / "briefs" / "brief.md"
    brief.parent.mkdir()
    brief.write_text(
        f"# Worker\n\n## Docs\n\n| Doc | Watch |\n|---|---|\n"
        f"| [Design]({doc}) | Relay comments |\n"
    )
    probe, cache = presence.Probe(), brief_cards.BriefCache()
    with db.connect() as conn:
        db.add(
            conn,
            "codex:b",
            "",
            metadata={"tty": "/dev/ttys002", "tmux_window": "3"},
            switch_source="tmux",
        )
        attached.attach(conn, "codex:b", brief)
        identity.ensure(conn, brief)
        before = ordered_active(conn, None, cache, probe, False, 1e20).cards["codex:b"]
        doc.rename(tmp_path / "moved-design.md")
        after = ordered_active(conn, None, cache, probe, False, 1e20 + 1e6).cards["codex:b"]

    assert before.mark == after.mark == "deaf"
    assert before.shown == after.shown == "deaf"


def test_changed_recipient_metadata_invalidates_confirmation(monkeypatch):
    monkeypatch.setattr(presence, "_harness_ttys", lambda: frozenset())
    monkeypatch.setattr(
        recipient, "_tty_commands", lambda tty: ["codex"] if tty.endswith("2") else []
    )
    row = _row("codex:b", "ttys002", created_at=10.0)
    probe, ids = presence.Probe(), {row.channel: "lemon-b.QuickOdd"}

    assert _MARKS(probe, [row], ids, 1000.0) == {row.channel: "deaf"}
    row = dataclasses.replace(row, metadata={"tty": "/dev/ttys003"})
    assert _MARKS(probe, [row], ids, 1001.0) == {row.channel: "dead"}


def test_an_idle_codex_lemon_with_a_harness_and_no_waiter_is_deaf(monkeypatch):
    row = _row("codex:b", "ttys002", created_at=10.0)

    assert _marks(monkeypatch, [row], frozenset({"ttys002"})) == {"codex:b": "deaf"}


def test_a_row_reported_after_the_listing_is_not_marked_dead(monkeypatch):
    row = _row("codex:b", "ttys002", created_at=2000.0)

    assert _marks(monkeypatch, [row], frozenset(), now=1000.0) == {"codex:b": "deaf"}


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
