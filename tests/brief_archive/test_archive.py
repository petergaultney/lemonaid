import sqlite3
from pathlib import Path

import pytest

from lemonaid import home
from lemonaid.audit import events
from lemonaid.brief import archive, attached, lemon
from lemonaid.inbox import db
from lemonaid.messages import store as messages

from .shared import LONG_AGO, brief, message, session


def test_the_brief_and_its_mailbox_move_to_the_month_it_was_last_used():
    path, lemon_id = brief("finished")
    session(path, "claude:finished")
    sent = message(lemon_id, LONG_AGO)

    with db.connect() as conn:
        moved = archive.archive(conn, path, LONG_AGO, why="test")
        assert lemon.brief_of(conn, lemon_id) == moved
        assert attached.by_channel(conn, ["claude:finished"]) == {}

    assert not path.exists() and "# finished" in moved.read_text()
    assert moved.parent.parent == archive.attic_dir()
    assert (moved.parent / "mailbox" / lemon_id / "1" / sent.name).read_text() == "Hello."
    assert not messages.mailbox_for_id(lemon_id).exists()


def test_a_brief_a_live_session_holds_stays_unless_that_session_is_closing():
    path, _ = brief("held")
    session(path, "claude:held", live=True)

    with db.connect() as conn:
        with pytest.raises(ValueError, match="live session"):
            archive.archive(conn, path, LONG_AGO, why="test")
        assert path.exists()

        assert archive.archive(conn, path, LONG_AGO, closing={"claude:held"}, why="test").exists()


def test_nothing_can_attach_the_brief_between_the_live_check_and_the_move(monkeypatch):
    path, _ = brief("raced")
    with db.connect() as conn:
        db.add(conn, "claude:raced", "", metadata={})
    check = archive._live_elsewhere
    attempts = []

    def check_then_attach(conn, *args):
        found = check(conn, *args)
        with db.connect(timeout=0.1) as other:
            try:
                attached.attach(other, "claude:raced", path)
                attempts.append("attached")
            except sqlite3.OperationalError:
                attempts.append("locked out")
        return found

    monkeypatch.setattr(archive, "_live_elsewhere", check_then_attach)
    with db.connect() as conn:
        archive.archive(conn, path, LONG_AGO, why="test")

    assert attempts == ["locked out"]


def test_a_home_migration_stops_archive_and_revive(monkeypatch, tmp_path):
    monkeypatch.setenv("LEMONAID_LEMONS_DIR", str(tmp_path / "lemons"))
    path, lemon_id = brief("paused")
    another, _ = brief("another")
    with db.connect() as conn:
        moved = archive.archive(conn, path, LONG_AGO, why="test")
    home.layout.lemons_dir().mkdir(parents=True, exist_ok=True)
    (home.layout.lemons_dir() / home.layout.MIGRATING).write_text("x\n")

    with db.connect() as conn:
        with pytest.raises(home.guard.Paused):
            archive.revive(conn, lemon_id, why="test")
        with pytest.raises(home.guard.Paused):
            archive.archive(conn, another, LONG_AGO, why="test")
    assert moved.exists() and another.exists()


def test_a_revived_brief_archives_again_into_the_same_month():
    path, lemon_id = brief("twice")
    mailbox = messages.mailbox_for_id(lemon_id)
    (mailbox / "done").mkdir(parents=True)
    (mailbox / "done" / "20261001T000000000000Z-read.md").write_text("Read.")
    with db.connect() as conn:
        archive.archive(conn, path, LONG_AGO, why="test")
    messages.send(messages.mailbox_for_id(lemon_id), "While away.", "claude:sender")

    with db.connect() as conn:
        archive.revive(conn, lemon_id, why="test")
        moved = archive.archive(conn, path, LONG_AGO, why="test")

    kept = moved.parent / "mailbox" / lemon_id / "1"
    assert {p.name for p in kept.rglob("*.md")} >= {"20261001T000000000000Z-read.md"}
    assert len(list(kept.glob("*.md"))) == 1
    assert not messages.mailbox_for_id(lemon_id).exists()


def test_a_failed_mailbox_move_leaves_the_brief_attached_and_where_it_was(monkeypatch):
    path, lemon_id = brief("stuck")
    session(path, "claude:stuck")
    mailbox = messages.mailbox_for_id(lemon_id)
    message(lemon_id, LONG_AGO)
    rename = Path.rename

    def refuse_the_mailbox(self, target):
        if self == mailbox:
            raise PermissionError("not writable")
        return rename(self, target)

    monkeypatch.setattr(Path, "rename", refuse_the_mailbox)
    with db.connect() as conn:
        with pytest.raises(PermissionError):
            archive.archive(conn, path, LONG_AGO, why="test")
        assert lemon.brief_of(conn, lemon_id) == path
        assert attached.by_channel(conn, ["claude:stuck"]) == {"claude:stuck": path}

    assert path.exists() and mailbox.is_dir()


def test_lemons_whose_ids_share_a_prefix_keep_their_own_messages():
    first, _ = brief("owner")
    second, _ = brief("owner-too")
    with db.connect() as conn:
        conn.execute(
            "UPDATE lemon_identities SET lemon_id = ? WHERE path = ?", ("review.owner", str(first))
        )
        conn.execute(
            "UPDATE lemon_identities SET lemon_id = ? WHERE path = ?",
            ("review.owner~2", str(second)),
        )
        conn.commit()
    mine = message("review.owner", LONG_AGO, "mine")
    message("review.owner~2", LONG_AGO, "theirs")
    with db.connect() as conn:
        archive.archive(conn, first, LONG_AGO, why="test")
        archive.archive(conn, second, LONG_AGO, why="test")
        archive.revive(conn, "review.owner", why="test")

    assert [p.name for p in messages.mailbox_for_id("review.owner").glob("*.md")] == [mine.name]
    assert [p for p in archive.attic_dir().rglob("*.md") if "review.owner~2" in p.parts]


def test_archive_and_revive_are_audited_with_where_the_brief_went_and_why():
    path, lemon_id = brief("audited")
    message(lemon_id, LONG_AGO)
    with db.connect() as conn:
        moved = archive.archive(conn, path, LONG_AGO, why="idle sweep: unused 14+ days")
        archive.revive(conn, lemon_id, why="by hand")

    archived, revived = events.entries(0, thing=lemon_id)
    assert (archived["action"], archived["why"]) == ("brief-archive", "idle sweep: unused 14+ days")
    assert (archived["from"], archived["to"]) == (str(path), str(moved))
    assert archived["mailbox"].startswith(str(moved.parent / "mailbox" / lemon_id))
    assert (revived["action"], revived["from"], revived["to"]) == (
        "brief-revive",
        str(moved),
        str(path),
    )


def test_a_refused_archive_records_nothing():
    path, _ = brief("held")
    session(path, "claude:held", live=True)
    with db.connect() as conn, pytest.raises(ValueError):
        archive.archive(conn, path, LONG_AGO, why="by hand")

    assert events.entries(0) == []
