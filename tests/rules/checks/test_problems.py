from lemonaid.rules import checks, patterns
from tests.rules import shared


def _problems(tmp_path, *fields: dict, rules: str = shared.RULES) -> list[str]:
    parsed = patterns.load(shared.write(tmp_path, *fields, rules=rules))
    assert parsed.problems == []
    return list(checks.problems(parsed.patterns))


def test_good_patterns_have_no_problems(tmp_path):
    assert _problems(tmp_path, shared.MERGE_ASK, shared.REVIEWER_ASK) == []


def test_a_regex_that_does_not_compile(tmp_path):
    [problem] = _problems(tmp_path, {**shared.MERGE_ASK, "regex": "(unclosed"})

    assert problem.startswith("merge-ask: regex does not compile")


def test_a_nested_quantifier_is_refused_without_running_the_examples(tmp_path):
    long_example = "a" * 40 + "!"

    problems = _problems(
        tmp_path,
        {**shared.MERGE_ASK, "regex": r"^(a+)+$", "no_match": [long_example]},
    )

    assert problems == [
        "merge-ask: regex nests one quantifier inside another, which can hang on a long message"
    ]


def test_every_example_is_checked(tmp_path):
    problems = _problems(
        tmp_path,
        {
            **shared.MERGE_ASK,
            "match": ["Want me to merge it?", "Merge it?"],
            "no_match": ["Should I merge main in?"],
        },
    )

    assert problems == [
        "merge-ask: does not match its match example 'Merge it?'",
        "merge-ask: matches its no_match example 'Should I merge main in?'",
    ]


def test_a_pattern_needs_an_example_of_each_kind(tmp_path):
    problems = _problems(tmp_path, {**shared.MERGE_ASK, "no_match": []})

    assert problems == ["merge-ask: needs at least one match and one no_match example"]


def test_a_tell_pattern_needs_say(tmp_path):
    problems = _problems(tmp_path, {**shared.REVIEWER_ASK, "mode": "tell"})

    assert problems == [
        "reviewer-ask: a tell pattern needs say, the line telling a lemon what to do"
    ]


def test_the_rule_must_start_exactly_one_paragraph_or_item(tmp_path):
    rules = shared.RULES + "\n- **A PR ready to merge gets the merge Status.** Said twice.\n"

    [twice] = _problems(tmp_path, shared.MERGE_ASK, rules=rules)
    [gone] = _problems(tmp_path, shared.MERGE_ASK, rules="# Rules\n")

    assert "2 paragraphs or list items" in twice
    assert "0 paragraphs or list items" in gone


def test_a_mention_inside_a_line_does_not_count_as_the_rule(tmp_path):
    rules = shared.RULES + "\nSee - **A PR ready to merge, above.\n"

    assert _problems(tmp_path, shared.MERGE_ASK, rules=rules) == []


def test_a_missing_rule_file(tmp_path):
    [problem] = _problems(tmp_path, {**shared.MERGE_ASK, "rule_file": "gone.md"})

    assert problem.startswith(f"merge-ask: cannot read rule_file {tmp_path / 'gone.md'}")


def test_an_example_that_backtracks_is_a_problem_not_a_hang(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "EXAMPLE_SECONDS", 0.05)

    problems = _problems(
        tmp_path,
        {**shared.MERGE_ASK, "regex": r"(a|aa)+$", "match": ["aa"], "no_match": ["a" * 60 + "!"]},
        {**shared.REVIEWER_ASK, "regex": r"a*a*a*a*a*b", "match": ["ab"], "no_match": ["a" * 400]},
    )

    assert problems == [
        f"merge-ask: took over 0.05 s on its no_match example {'a' * 60 + '!'!r}",
        f"reviewer-ask: took over 0.05 s on its no_match example {'a' * 400!r}",
    ]
