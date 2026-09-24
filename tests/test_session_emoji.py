"""Where a session's emoji shows: before its name on inbox rows and cards."""

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import _decorated_name


def test_a_card_name_starts_with_its_sessions_emoji():
    decorated = db.Notification(id=1, channel="claude:x", message="", name="tenant views")
    plain = db.Notification(id=2, channel="claude:y", message="", name="other")

    emojis = {"claude:x": "🦫"}
    assert _decorated_name(decorated, emojis) == "🦫 tenant views"
    assert _decorated_name(plain, emojis) == "other"
