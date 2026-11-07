import time

import pytest

from lemonaid.brief import archive, lemon
from lemonaid.inbox import db
from lemonaid.messages import store as messages

from .shared import LONG_AGO, brief, message


def test_revive_puts_back_the_brief_and_every_message_kept_or_sent_since():
    path, lemon_id = brief("returning")
    kept = message(lemon_id, LONG_AGO)
    with db.connect() as conn:
        archive.archive(conn, path, LONG_AGO, why="test")
    new = messages.send(messages.mailbox_for_id(lemon_id), "Welcome back.", "claude:sender")

    with db.connect() as conn:
        assert archive.revive(conn, lemon_id, why="test") == path
        assert lemon.brief_of(conn, lemon_id) == path

    names = {p.name for p in messages.mailbox_for_id(lemon_id).glob("*.md")}
    assert {kept.name, new.name} <= names


def test_reviving_a_brief_that_was_never_archived_refuses():
    _, lemon_id = brief("here", at=time.time())

    with db.connect() as conn, pytest.raises(LookupError):
        archive.revive(conn, lemon_id, why="test")


def test_revive_brings_back_messages_archived_under_the_old_attic_folder():
    path, lemon_id = brief("returning")
    with db.connect() as conn:
        moved = archive.archive(conn, path, LONG_AGO, why="test")
    old = moved.parent / "inbox" / lemon_id / "1"
    old.mkdir(parents=True)
    (old / "20261001T000000000000Z-kept.md").write_text("Kept.")

    with db.connect() as conn:
        archive.revive(conn, lemon_id, why="test")

    assert (messages.mailbox_for_id(lemon_id) / "20261001T000000000000Z-kept.md").exists()
    assert not (moved.parent / "inbox" / lemon_id).exists()


def test_revive_finds_a_brief_in_the_attic_whose_record_still_names_the_briefs_directory():
    path, lemon_id = brief("stranded")
    with db.connect() as conn:
        moved = archive.archive(conn, path, LONG_AGO, why="test")
        conn.execute(
            "UPDATE lemon_identities SET path = ? WHERE lemon_id = ?", (str(path), lemon_id)
        )
        conn.commit()

    with db.connect() as conn:
        assert archive.revive(conn, lemon_id, why="test") == path
        assert lemon.brief_of(conn, lemon_id) == path

    assert path.exists() and not moved.exists()


def test_revive_will_not_restore_another_lemons_brief_of_the_same_file_name():
    path, _ = brief("shared-name")
    with db.connect() as conn:
        archive.archive(conn, path, LONG_AGO, why="test")
    path, second = brief("shared-name")
    path.unlink()

    with db.connect() as conn, pytest.raises(LookupError):
        archive.revive(conn, second, why="test")

    assert not path.exists()


def test_revive_refuses_when_two_attic_months_hold_the_lemons_brief():
    path, lemon_id = brief("twice")
    with db.connect() as conn:
        moved = archive.archive(conn, path, LONG_AGO, why="test")
        conn.execute(
            "UPDATE lemon_identities SET path = ? WHERE lemon_id = ?", (str(path), lemon_id)
        )
        conn.commit()
    other = moved.parent.parent / "2020-01" / moved.name
    other.parent.mkdir()
    other.write_text(moved.read_text())

    with db.connect() as conn, pytest.raises(LookupError):
        archive.revive(conn, lemon_id, why="test")
