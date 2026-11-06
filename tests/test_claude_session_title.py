"""Tests for lemonaid.claude.session_title."""

import pytest

from lemonaid.claude import session_title
from lemonaid.inbox import db, emoji


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "inbox.db"))
    with db.connect() as connection:
        yield connection


@pytest.mark.parametrize(
    ("name", "session_emoji", "wordybin", "expected"),
    [
        ("fix pager", "🍋", "BlessBar", "🍋 fix pager (BlessBar)"),
        ("fix pager", "", "BlessBar", "fix pager (BlessBar)"),
        ("fix pager", "🍋", "", "🍋 fix pager"),
        ("fix pager", "", "", ""),
        ("2026 plan", "🍋", "", "🍋 2026 plan"),
        ("🍋 fix pager (BlessBar)", "🍋", "BlessBar", "🍋 fix pager (BlessBar)"),
        ("🍋 fix pager (BlessBar)", "🐝", "BlessBar", "🐝 fix pager (BlessBar)"),
        ("1️⃣ fix pager (BlessBar)", "1️⃣", "BlessBar", "1️⃣ fix pager (BlessBar)"),
    ],
)
def test_build(name: str, session_emoji: str, wordybin: str, expected: str):
    assert session_title.build(name, session_emoji, wordybin) == expected


@pytest.mark.parametrize("session_emoji", ["🍋", "1️⃣", "🐝"])
def test_a_pushed_title_imported_as_the_name_does_not_grow(conn, session_emoji: str):
    channel = "claude:abc12345"
    db.register_working(
        conn, channel=channel, message="m", name="fix pager", metadata={}, switch_source=None
    )
    emoji.set_emoji(conn, channel, session_emoji)

    pushed = session_title.pending(conn, channel, "")
    imported = session_title.canonical(conn, channel, pushed)

    assert imported == "fix pager"
    assert session_title.build(imported, session_emoji, "") == pushed


def test_a_changed_emoji_replaces_the_one_in_the_imported_title(conn):
    channel = "claude:abc12345"
    db.register_working(
        conn, channel=channel, message="m", name="fix pager", metadata={}, switch_source=None
    )
    emoji.set_emoji(conn, channel, "🍋")
    pushed = session_title.pending(conn, channel, "")
    emoji.set_emoji(conn, channel, "🐝")

    assert session_title.canonical(conn, channel, pushed) == "fix pager"
    assert session_title.pending(conn, channel, pushed) == "🐝 fix pager"


def test_a_session_without_emoji_or_brief_keeps_its_name(conn):
    assert session_title.canonical(conn, "claude:abc12345", "🍋 mine (x)") == "🍋 mine (x)"
