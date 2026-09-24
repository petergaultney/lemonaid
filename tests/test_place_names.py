"""Persistent, distinctive identities for managed places."""

from string import ascii_uppercase

from lemonaid.places import names
from lemonaid.places.ssa_top_names import SSA_TOP_1000_2024


def test_every_letter_has_a_pool_and_no_pool_name_is_common():
    assert set(names.NAME_POOLS) == set(ascii_uppercase)
    assert not ({name.casefold() for name in names.POOL_NAMES} & SSA_TOP_1000_2024)


def test_distinctive_words_choose_letters_before_shared_words():
    peers = ["protostellar-tenant-views", "protostellar-lightdash"]

    assert names.candidate_letters("protostellar-tenant-views", peers)[:2] == ["T", "V"]
    assert names.candidate_letters("protostellar-lightdash", peers)[:1] == ["L"]


def test_every_shared_word_falls_back_to_the_first_word():
    peers = ["mops-pull-queue", "mops-pull-queue"]

    assert names.candidate_letters("mops-pull-queue", peers)[0] == "M"


def test_assignment_is_idempotent_for_an_active_place(tmp_path):
    place = tmp_path / "protostellar" / "tenant-views"
    place.mkdir(parents=True)

    first = names.assign(
        place,
        "protostellar-tenant-views",
        peers=["protostellar-tenant-views", "protostellar-lightdash"],
    )
    second = names.assign(place, "a-completely-different-name", peers=[])

    assert first == "Tapir"
    assert second == first
    assert names.current_name(place) == first


def test_different_places_never_receive_the_same_name(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()

    assert names.assign(first, "thing-one", peers=[]) == "Tapir"
    assert names.assign(second, "thing-two", peers=[]) == "Tarsier"


def test_retired_name_is_never_reused_even_at_the_same_path(tmp_path):
    place = tmp_path / "thing"
    place.mkdir()
    first = names.assign(place, "thing", peers=[])

    names.retire([place])
    second = names.assign(place, "thing", peers=[])

    assert first == "Tapir"
    assert second == "Tarsier"
    assert names.current_name(place) == second


def test_fallback_remains_unique_after_the_pool_is_exhausted(monkeypatch):
    monkeypatch.setattr(names, "NAME_POOLS", {})
    monkeypatch.setattr(names, "POOL_NAMES", ())

    assert names._choose_name("anything", [], set()) == "Lemon-1"
    assert names._choose_name("anything", [], {"Lemon-1"}) == "Lemon-2"
