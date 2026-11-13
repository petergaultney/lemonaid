import datetime
import os
import time

import pytest

from lemonaid.po_box import cards, inbox

_NOW = datetime.datetime.now(datetime.UTC)


@pytest.fixture
def card(tmp_path):
    return cards.register(tmp_path / "lemon-post", "sam", "plan.BlessBar", "Plan", "", _NOW)


def test_receiving_labels_the_message_moves_it_to_read_and_keeps_a_local_copy(card, tmp_path):
    local = tmp_path / "mailbox" / "plan.BlessBar"
    sent = inbox.send(card, "Please look at the PR.", "kim: other.AuditInk")

    claimed, text = inbox.take_next(card.inbox, local, keep_days=7)

    assert text.startswith(inbox.LABEL) and "From: kim: other.AuditInk" in text
    assert text.endswith("Please look at the PR.\n")
    assert claimed == card.inbox / inbox.READ / sent.name
    assert (local / "done" / sent.name).read_text() == text
    assert inbox.pending(card.inbox) == []
    assert inbox.take_next(card.inbox, local, keep_days=7) is None


def test_read_messages_older_than_the_limit_are_deleted(card, tmp_path):
    old, _ = inbox.claim(inbox.send(card, "old", "kim"), tmp_path / "local", keep_days=7)
    stale = time.time() - 8 * 86400
    os.utime(old, (stale, stale))

    kept, _ = inbox.claim(inbox.send(card, "new", "kim"), tmp_path / "local", keep_days=7)

    assert not old.exists() and kept.exists()


def test_oversized_messages_are_refused_and_never_delivered_whole(card, tmp_path):
    with pytest.raises(ValueError, match="at most"):
        inbox.send(card, "x" * (inbox.MAX_BYTES + 1), "kim")

    planted = card.inbox / "20261111T000000000000Z-big.md"
    planted.write_text("y" * 2_000_000)
    _, text = inbox.take_next(card.inbox, tmp_path / "local", keep_days=7)
    assert "was not delivered" in text and "yyyy" not in text
    assert (tmp_path / "local" / "done" / planted.name).stat().st_size < 1000


def test_a_message_that_isnt_utf8_is_received_as_a_notice_and_the_next_one_follows(card, tmp_path):
    (card.inbox / "000-bad.md").write_bytes(b"\xff not text")
    inbox.send(card, "Still arrives", "kim")
    local = tmp_path / "local"

    _, first = inbox.take_next(card.inbox, local, keep_days=7)
    _, second = inbox.take_next(card.inbox, local, keep_days=7)

    assert "isn't UTF-8" in first and second.endswith("Still arrives\n")


def test_a_claim_that_cannot_record_locally_leaves_the_message_pending(card, tmp_path):
    sent = inbox.send(card, "Keep me", "kim")
    local = tmp_path / "local"
    local.mkdir()
    (local / "done").write_text("a file where the folder should be")

    with pytest.raises(OSError):
        inbox.take_next(card.inbox, local, keep_days=7)

    assert inbox.pending(card.inbox) == [sent]


def test_an_inbox_whose_read_folder_is_a_link_is_left_alone(card, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (card.inbox / inbox.READ).symlink_to(outside)
    inbox.send(card, "hello", "kim")

    assert inbox.pending(card.inbox) == []
    assert inbox.take_next(card.inbox, tmp_path / "local", keep_days=7) is None


def test_unread_messages_move_to_the_local_mailbox_still_labeled(card, tmp_path):
    inbox.send(card, "one", "kim")
    inbox.send(card, "two", "kim")
    local = tmp_path / "local"

    assert inbox.unread_to_local(card.inbox, local) == 2

    assert inbox.pending(card.inbox) == []
    texts = [p.read_text() for p in sorted(local.glob("*.md"))]
    assert all(t.startswith(inbox.LABEL) for t in texts) and texts[1].endswith("two\n")


def test_a_cleanup_failure_after_the_move_still_delivers_the_message(card, tmp_path, monkeypatch):
    inbox.send(card, "Deliver me", "kim")

    def refuse(read_dir, keep_days):
        raise PermissionError("read-only")

    monkeypatch.setattr(inbox, "_forget_old", refuse)

    _, text = inbox.take_next(card.inbox, tmp_path / "local", keep_days=7)
    assert text.endswith("Deliver me\n")
