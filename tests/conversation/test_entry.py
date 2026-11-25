"""Lines of a conversation, whichever harness recorded them."""

from lemonaid.conversation import entry


def test_newest_counts_messages_and_keeps_the_tool_calls_among_them():
    found = [
        entry.Entry(entry.USER, "first", ""),
        entry.Entry(entry.TOOL, "ls", ""),
        entry.Entry(entry.LEMON, "second", ""),
        entry.Entry(entry.TOOL, "make", ""),
        entry.Entry(entry.TOOL, "make test", ""),
        entry.Entry(entry.OTHER, "third", "", "mail"),
    ]

    assert [each.text for each in entry.newest(found, 2)] == [
        "second",
        "make",
        "make test",
        "third",
    ]
    assert entry.newest(found, 5) == found
