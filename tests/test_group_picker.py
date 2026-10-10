from lemonaid.inbox.tui import group_picker


def test_typing_narrows_the_groups_and_offers_a_new_one_unless_named_exactly():
    names = ["Inbox work", "Relay", "Review"]

    assert group_picker.choices(names, "") == [(n, n) for n in names]
    assert [label for _, label in group_picker.choices(names, "re")] == [
        "Relay",
        "Review",
        "New group: re",
    ]
    assert group_picker.choices(names, " Relay ") == [("Relay", "Relay")]
