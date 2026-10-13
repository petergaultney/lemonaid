"""Suggested name words: parsing them, and the names they make in order."""

import random

import wordybin

from lemonaid.brief import name_words


def test_parse_splits_by_length_and_keeps_order_without_repeats():
    words = name_words.parse("audit, ink check,AUDIT  web review ok re-do")

    assert words.fives == ("audit", "check")
    assert words.threes == ("ink", "web")
    assert words.malformed == ("review", "ok", "re-do")


def test_shaped_title_cases_a_five_plus_three_name_and_refuses_anything_else():
    assert name_words.shaped("auditINK") == "AuditInk"
    assert [name_words.shaped(n) for n in ("Audit", "AuditInks", "Aud1tInk", "Audit-In")] == [
        "",
        "",
        "",
        "",
    ]


def test_read_takes_the_header_line_only():
    header = "# lead\n\nBrief-ID: lead.CarryLeg\nName words: audit ink\n\n## Goal\n"

    assert name_words.read(header) == name_words.Words(("audit",), ("ink",))
    assert name_words.read("# lead\n\n## Goal\n\nName words: audit ink\n") is None


def test_problems_names_each_malformed_word():
    assert name_words.problems("# lead\nName words: audit review ok\n") == [
        "`Name words:` review, ok is not five or three letters"
    ]
    assert name_words.problems("# lead\nName words: audit ink\n") == []


def test_names_go_best_first_by_the_sum_of_places():
    words = name_words.Words(("audit", "check"), ("ink", "web"))

    assert list(name_words.names(words, random.Random(0))) == [
        "AuditInk",
        "AuditWeb",
        "CheckInk",
        "CheckWeb",
    ]


def test_a_missing_length_is_filled_from_every_wordybin_word():
    names = list(name_words.names(name_words.Words(fives=("zzzzz",)), random.Random(0)))

    assert len(set(names)) == 128
    assert all(n.startswith("Zzzzz") for n in names)
    assert all(wordybin.encode(wordybin.decode("Carry" + n[5:]))[5:] == n[5:] for n in names)


def test_no_words_make_no_names():
    assert list(name_words.names(name_words.NONE, random.Random(0))) == []
