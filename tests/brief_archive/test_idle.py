import time

from lemonaid.brief import archive
from lemonaid.inbox import db

from .shared import DAY, brief, message, session


def _idle_names(days: float = 14) -> list[str]:
    with db.connect() as conn:
        return [i.path.stem for i in archive.idle(conn, days, time.time())]


def test_a_brief_untouched_and_unattached_for_the_window_is_idle():
    brief("old")
    brief("fresh", at=time.time())

    assert _idle_names() == ["old"]


def test_a_live_session_keeps_even_an_old_brief_in_use():
    path, _ = brief("held")
    session(path, "claude:held", live=True)

    assert _idle_names() == []


def test_recent_activity_on_an_archived_session_keeps_it_in_use():
    path, _ = brief("recent")
    session(path, "claude:recent", at=time.time() - DAY)

    assert _idle_names() == []


def test_a_recent_message_in_its_inbox_keeps_it_in_use():
    _, lemon_id = brief("messaged")
    message(lemon_id, time.time() - DAY)

    assert _idle_names() == []
