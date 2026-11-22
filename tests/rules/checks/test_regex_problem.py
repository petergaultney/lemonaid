import pytest

from lemonaid.rules import checks


@pytest.mark.parametrize(
    "regex",
    [
        r"(\w+\s?)+",
        r"(?:a|b+)*",
        r"(?>a+)+",
        r"(?:x(?=(a+)+))*",
        r"(?:a{1,3})+",
    ],
)
def test_a_variable_repeat_inside_a_repeat_can_hang(regex):
    assert "nests one quantifier" in checks.regex_problem(regex)


@pytest.mark.parametrize(
    "regex",
    [
        r"\d+",
        r"(?: (?!second\b)\w+)?",  # an optional group runs at most once
        r"(?:a{2})+",  # a fixed count inside a repeat can't backtrack
        r"(?i)\bwant me to merge\b|^\s*(?:\*\*)?merge #\d+\?",
    ],
)
def test_other_regexes_can_run(regex):
    assert checks.regex_problem(regex) == ""


def test_a_regex_that_does_not_compile():
    assert checks.regex_problem("(").startswith("regex does not compile")
