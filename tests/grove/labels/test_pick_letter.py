from lemonaid.grove.layout.labels import pick_letter


def test_prefers_word_initials_then_other_letters():
    assert pick_letter("dev harness", set()) == "d"
    assert pick_letter("dev harness", {"d"}) == "h"
    assert pick_letter("dev harness", {"d", "h"}) == "e"


def test_never_gives_out_the_leads_letter():
    assert pick_letter("lemon", set()) == "e"


def test_a_capitalized_name_still_gets_a_lowercase_letter():
    assert pick_letter("Stray inbox cards", {"s"}) == "i"
    assert pick_letter("Stray inbox cards", set()) == "s"


def test_only_plain_letters_are_given():
    assert pick_letter("été 2026", set()) == "t"
