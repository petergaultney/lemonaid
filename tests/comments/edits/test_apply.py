from lemonaid.comments import edits


def test_inserts_at_the_same_offset_keep_their_order() -> None:
    edit_list = [edits.Edit(1, 1, "x"), edits.Edit(3, 3, "first"), edits.Edit(3, 3, "second")]

    result = edits.apply("abc", edit_list)

    assert result == "axbcfirstsecond"


def test_a_replacement_is_applied_against_the_original_offsets() -> None:
    result = edits.apply("hello world", [edits.Edit(0, 5, "goodbye"), edits.Edit(6, 11, "moon")])

    assert result == "goodbye moon"
