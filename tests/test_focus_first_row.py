from lemonaid import groups
from lemonaid.inbox import db, sections
from lemonaid.inbox.tui import focus


def _row(i: int, channel: str) -> sections.Row:
    return sections.Row(str(i), db.Notification(i, channel, ""))


def test_first_row_is_the_first_drawn_row_of_a_focused_channel() -> None:
    header = sections.Header(groups.store.Group(1, "g", 0, (), False, "#c8a0f0"), 2, "read")
    entries = [header, _row(1, "claude:a"), _row(2, "claude:b"), _row(3, "claude:b")]

    assert focus.first_row(entries, frozenset({"claude:b"})) == 2


def test_first_row_is_none_when_no_focused_lemon_is_drawn() -> None:
    assert focus.first_row([_row(1, "claude:a")], frozenset({"claude:z"})) is None
