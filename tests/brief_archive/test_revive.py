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
        archive.archive(conn, path, LONG_AGO)
    new = messages.send(messages.inbox_for_id(lemon_id), "Welcome back.", "claude:sender")

    with db.connect() as conn:
        assert archive.revive(conn, lemon_id) == path
        assert lemon.brief_of(conn, lemon_id) == path

    names = {p.name for p in messages.inbox_for_id(lemon_id).glob("*.md")}
    assert {kept.name, new.name} <= names


def test_reviving_a_brief_that_was_never_archived_refuses():
    _, lemon_id = brief("here", at=time.time())

    with db.connect() as conn, pytest.raises(LookupError):
        archive.revive(conn, lemon_id)
