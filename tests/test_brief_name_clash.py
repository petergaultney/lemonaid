"""A lemon coming back to a name another active lemon holds is warned once, and never stopped."""

import pytest

from lemonaid.brief import identity, name_clash, store
from lemonaid.inbox import db
from lemonaid.messages import store as message_store


def _brief(lemon_id: str) -> None:
    path = store.briefs_dir() / f"{lemon_id.split('.')[0]}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# x\n\nBrief-ID: {lemon_id}\n")
    with db.connect() as conn:
        identity.ensure(conn, path)


@pytest.fixture(autouse=True)
def _two_lemons_one_name():
    _brief("one.AuditInk")
    _brief("two.AuditInk")


def _pending(lemon_id: str) -> list[str]:
    return [p.read_text() for p in message_store.inbox_for_id(lemon_id).glob("*.md")]


def test_the_warning_is_queued_once_however_often_the_lemon_comes_back():
    with db.connect() as conn:
        first = name_clash.warn(conn, "one.AuditInk")
        second = name_clash.warn(conn, "one.AuditInk")

    assert first == second
    assert "also the name of two.AuditInk" in first
    assert len(_pending("one.AuditInk")) == 1


def test_a_failure_to_queue_the_warning_is_not_raised(monkeypatch):
    def refuse(*_args):
        raise OSError("read-only inbox")

    monkeypatch.setattr(message_store, "send", refuse)
    with db.connect() as conn:
        assert "also the name of two.AuditInk" in name_clash.warn(conn, "one.AuditInk")


def test_a_name_held_by_no_one_else_warns_nothing():
    with db.connect() as conn:
        assert name_clash.warn(conn, "three.CheckWeb") == ""
    assert _pending("three.CheckWeb") == []
