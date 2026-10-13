"""Which names active lemons hold: a live session, or activity within the idle window."""

import os
import time

from lemonaid.brief import active_names, attached, identity, store
from lemonaid.inbox import db

_DAY = 24 * 60 * 60


def _lemon(lemon_id: str, channel: str = "", idle_days: float = 0) -> None:
    path = store.briefs_dir() / f"{lemon_id.split('.')[0]}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# x\n\nBrief-ID: {lemon_id}\n")
    then = time.time() - idle_days * _DAY
    os.utime(path, (then, then))
    with db.connect() as conn:
        identity.ensure(conn, path)
        if channel:
            db.add(conn, channel, "", metadata={})
            attached.attach(conn, channel, path)
            conn.execute(
                "UPDATE notifications SET created_at = ? WHERE channel = ?", (then, channel)
            )
            conn.commit()


def _held() -> dict[str, set[str]]:
    with db.connect() as conn:
        return active_names.holders(conn, active_names.window_start(14, time.time()))


def test_a_brief_idle_past_the_window_frees_its_name():
    _lemon("recent.AuditInk", idle_days=3)
    _lemon("stale.CheckWeb", idle_days=20)

    assert _held() == {"auditink": {"recent.AuditInk"}}


def test_a_live_session_holds_an_old_brief_s_name():
    _lemon("stale.CheckWeb", "claude:live", idle_days=20)

    assert _held() == {"checkweb": {"stale.CheckWeb"}}


def test_an_archived_session_holds_the_name_until_the_window_passes():
    _lemon("recent.AuditInk", "claude:recent", idle_days=3)
    _lemon("stale.CheckWeb", "claude:stale", idle_days=20)
    with db.connect() as conn:
        db.archive_channel(conn, "claude:recent", "test")
        db.archive_channel(conn, "claude:stale", "test")

    assert _held() == {"auditink": {"recent.AuditInk"}}


def test_an_alias_holds_its_name_for_the_lemon_it_points_to():
    _lemon("lead.AuditInk", idle_days=1)
    with db.connect() as conn:
        conn.execute("INSERT INTO lemon_aliases VALUES ('lead.CheckWeb', 'lead.AuditInk')")
        conn.commit()

    assert _held() == {"auditink": {"lead.AuditInk"}, "checkweb": {"lead.AuditInk"}}


def test_zero_idle_days_holds_every_name():
    _lemon("stale.CheckWeb", idle_days=400)
    with db.connect() as conn:
        assert active_names.holders(conn, active_names.window_start(0, time.time())) == {
            "checkweb": {"stale.CheckWeb"}
        }


def test_shared_and_the_warning_name_the_other_lemons():
    _lemon("one.AuditInk", idle_days=1)
    _lemon("two.AuditInk", idle_days=1)
    _lemon("three.CheckWeb", idle_days=1)

    assert active_names.shared(_held()) == {"auditink": {"one.AuditInk", "two.AuditInk"}}
    with db.connect() as conn:
        others = active_names.sharing(conn, "one.AuditInk")
    assert others == ["two.AuditInk"]
    assert "also the name of two.AuditInk" in active_names.warning("one.AuditInk", others)
    assert active_names.warning("three.CheckWeb", []) == ""
