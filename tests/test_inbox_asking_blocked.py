"""A lemon stuck on a permission prompt is placed and drawn `blocked`, whatever its brief says."""

import time

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db, presence, view
from lemonaid.inbox.tui.rows.brief_cards import BriefCache


def _session(conn, name: str, kind: str) -> str:
    channel = f"claude:{name}"
    db.add(
        conn,
        channel,
        "a message",
        name,
        {"tty": f"/dev/ttys-{name}", "cwd": "/tmp", "session_id": name, "notification_type": kind},
        switch_source="tmux",
    )
    return channel


def _brief(conn, channel: str, status: str) -> None:
    stem = f"work-{channel.split(':')[1]}"
    path = brief_store.briefs_dir() / f"2026-10-12-{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Work\n\nBrief-ID: {stem}.SampleBin\n\nStatus: {status}\n\n## Now\n")
    identity.ensure(conn, path)
    attached.attach(conn, channel, path)


def test_a_lemon_stuck_on_a_prompt_is_blocked_with_or_without_a_brief():
    with db.connect() as conn:
        merging = _session(conn, "merging", "Stop")
        _brief(conn, merging, "merge")
        stuck = _session(conn, "stuck", "permission_prompt")
        _brief(conn, stuck, "running")
        briefless = _session(conn, "briefless", "PermissionRequest")
        active = view.ordered_active(
            conn, "tmux", BriefCache(), presence.Probe(), False, time.time()
        )

    statuses = view.statuses(active.cards, active.rows)
    assert (statuses[stuck], statuses[briefless], statuses[merging]) == (
        "blocked",
        "blocked",
        "merge",
    )
    assert active.cards[stuck].shown == "blocked"
    assert [n.channel for n in active.rows][-1] == merging


def test_the_prompt_no_longer_blocks_once_the_transcript_moves_past_it():
    with db.connect() as conn:
        stuck = _session(conn, "stuck", "permission_prompt")
        _brief(conn, stuck, "running")
        row = db.get_by_channel(conn, stuck, unread_only=False)
        db.mark_read(conn, row.id)
        db.record_turn(conn, stuck, row.created_at + 5)
        active = view.ordered_active(
            conn, "tmux", BriefCache(), presence.Probe(), False, time.time()
        )

    assert view.statuses(active.cards, active.rows)[stuck] == "running"
