"""A Codex lemon's inbox name becomes the title Codex has for its thread."""

from lemonaid.inbox import db, emoji
from lemonaid.inbox.tui.watchers import session_names
from tests import codex_fakes


def _add(name: str, session_id: str = "abc", channel: str = "") -> None:
    with db.connect() as conn:
        db.add(
            conn,
            channel or f"codex:{session_id}",
            "hi",
            name=name,
            metadata={"session_id": session_id, "name_source": "environment"},
        )


def _name() -> str:
    with db.connect() as conn:
        return db.get_active(conn, switch_source=None)[0].name


def test_placeholder_name_becomes_codex_s_title(codex_records) -> None:
    _add("spatial-lemon-jump")
    codex_records["abc"] = codex_fakes.thread("abc", name="Review #418 grove")

    assert session_names.upgrade({}) is True
    assert _name() == "Review #418 grove"


def test_the_name_lemonaid_gave_the_thread_comes_back_bare(codex_records) -> None:
    _add("spatial-lemon-jump")
    with db.connect() as conn:
        emoji.set_emoji(conn, "codex:abc", "🦊")
    codex_records["abc"] = codex_fakes.thread("abc", name="🦊 Review #418 grove")

    session_names.upgrade({})
    assert _name() == "Review #418 grove"


def test_an_untitled_thread_keeps_its_placeholder(codex_records) -> None:
    _add("spatial-lemon-jump")
    codex_records["abc"] = codex_fakes.thread("abc")

    assert session_names.upgrade({}) is False
    assert _name() == "spatial-lemon-jump"


def test_a_user_rename_stays_visible(codex_records) -> None:
    _add("spatial-lemon-jump")
    with db.connect() as conn:
        db.update_name(conn, db.get_active(conn, switch_source=None)[0].id, "mine")
    codex_records["abc"] = codex_fakes.thread("abc", name="Codex title")

    session_names.upgrade({})
    assert _name() == "mine"


def test_a_reconciled_row_is_titled_by_its_session_id(codex_records) -> None:
    _add("spatial-lemon-jump", session_id="abc", channel="codex:transient")
    codex_records["abc"] = codex_fakes.thread("abc", name="Title")

    session_names.upgrade({})
    assert _name() == "Title"
