import pytest

from lemonaid.watch import lemon_signature, roles, shared_signer, signature


def test_a_name_is_spaced_at_its_second_capital():
    assert signature.spaced("FilmyBoy") == "Filmy Boy"
    assert signature.spaced("Filmy Boy") == "Filmy Boy"
    assert signature.sign("FilmyBoy", "Author", in_relay=True) == "Filmy Boy (Author)"
    assert signature.sign("Filmy Boy", "Author") == "FilmyBoy (Author)"


@pytest.mark.parametrize(
    "spelling",
    ["FilmyBoy (Author)", "Filmy Boy (Author)", "Author (FilmyBoy)", "Author (Filmy Boy)"],
)
def test_every_spelling_of_a_signature_matches_every_other(spelling):
    assert signature.forms(["FilmyBoy (Author)"]) == signature.forms([spelling])
    assert spelling in signature.forms(["FilmyBoy (Author)"])


def test_a_harness_name_is_kept_as_given():
    assert signature.forms(["Claude"]) == {"Claude"}


def test_a_github_comment_signed_in_either_order_is_mine():
    assert lemon_signature.is_signed("🍋 FilmyBoy (Author): done", ["Author (FilmyBoy)"])
    assert lemon_signature.is_signed("🍋 Author (FilmyBoy): done", ["FilmyBoy (Author)"])
    assert not lemon_signature.is_signed("🍋 SunnyNow (Author): done", ["FilmyBoy (Author)"])


def test_a_reviewer_is_recognised_in_either_order():
    assert roles.derive("", "FilmyBoy (Reviewer)", False, False) == "reviewer"
    assert roles.derive("", "Filmy Boy (Reviewer)", False, False) == "reviewer"
    assert roles.derive("", "Reviewer (FilmyBoy)", False, False) == "reviewer"
    assert roles.derive("", "FilmyBoy (Author)", False, False) == "author"


def test_the_shared_signer_check_reads_the_name_from_a_spaced_signature():
    assert shared_signer.warning("Filmy Boy (Reviewer)") == ""
