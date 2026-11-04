import threading

import pytest

from lemonaid.messages import receipts, store


def _send(mailbox, body: str, key: str = "ab12"):
    return lambda: store.send(mailbox, body, "me", key)


def test_a_keyed_message_is_replaced_while_pending_and_never_after_it_is_received():
    mailbox = store.mailbox_for_id("Work.alpha")
    store.send(mailbox, "first", "me", "ab12")
    pending = receipts.by_key("ab12")

    replaced = receipts.resend(mailbox, "ab12", _send(mailbox, "second"))
    [waiting] = [p.read_text() for p in mailbox.glob("*.md")]
    claimed, _ = store.take_next(mailbox)
    again = receipts.resend(mailbox, "ab12", _send(mailbox, "third"))

    assert pending == receipts.PENDING and replaced
    assert "second" in waiting
    assert receipts.by_key("ab12").startswith("delivered ")
    assert receipts.receipt(receipts.message_id(claimed)).startswith("delivered ")
    assert not again and list(mailbox.glob("*.md")) == []


def test_a_resend_waits_for_a_receiver_and_sends_nothing_once_it_received_the_copy():
    mailbox = store.mailbox_for_id("Work.alpha")
    store.send(mailbox, "first", "me", "ab12")
    result: list[bool] = []
    with store.receive_lock(mailbox):
        resending = threading.Thread(
            target=lambda: result.append(receipts.resend(mailbox, "ab12", _send(mailbox, "x")))
        )
        resending.start()
        resending.join(0.3)
        blocked = resending.is_alive()
        found = store.peek_next(mailbox)
        assert found is not None
        store.mark_done(found[0])  # as a receiver does, holding the lock
    resending.join(5)

    assert blocked and result == [False]
    assert list(mailbox.glob("*.md")) == []


def test_a_key_must_be_hex_and_an_odd_id_is_unknown():
    mailbox = store.mailbox_for_id("Work.alpha")

    with pytest.raises(ValueError, match="hex"):
        store.send(mailbox, "body", "me", "../x")
    with pytest.raises(ValueError, match="key"):
        receipts.resend(mailbox, "../*", _send(mailbox, "x"))
    assert receipts.receipt("../*") == receipts.UNKNOWN
