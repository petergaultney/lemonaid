from pathlib import Path

from lemonaid.rules import patterns
from tests.rules import shared


def test_a_pattern_reads_its_rule_file_beside_the_pattern_file(tmp_path):
    parsed = patterns.load(shared.write(tmp_path, shared.MERGE_ASK))

    assert parsed.problems == []
    [found] = parsed.patterns
    assert found.id == "merge-ask"
    assert found.rule_file == tmp_path / "rules.md"
    assert found.match == tuple(shared.MERGE_ASK["match"])


def test_mode_defaults_to_report_and_cwd_to_anywhere(tmp_path):
    [found] = patterns.load(shared.write(tmp_path, shared.REVIEWER_ASK)).patterns

    assert (found.mode, found.say, found.cwd) == ("report", "", "")


def test_a_home_relative_rule_file_is_expanded(tmp_path):
    [found] = patterns.parse(
        "\n".join(
            [
                "[[pattern]]",
                'id = "x"',
                'regex = "x"',
                'rule_file = "~/notes/rules.md"',
                'rule_starts = "x"',
            ]
        ),
        tmp_path,
    ).patterns

    assert found.rule_file == Path.home() / "notes" / "rules.md"


def test_an_unknown_key_or_mode_is_a_problem_and_leaves_the_pattern_out(tmp_path):
    parsed = patterns.load(
        shared.write(tmp_path, {**shared.MERGE_ASK, "mode": "shout", "no-match": ["x"]})
    )

    assert parsed.patterns == []
    assert parsed.problems == [
        "merge-ask: unknown key 'no-match'",
        "merge-ask: mode must be one of report, tell",
    ]


def test_a_missing_required_key_is_a_problem(tmp_path):
    fields = {key: value for key, value in shared.MERGE_ASK.items() if key != "rule_starts"}

    assert patterns.load(shared.write(tmp_path, fields)).problems == [
        "merge-ask: rule_starts must be a non-empty string"
    ]


def test_ids_are_unique_even_across_patterns_left_out(tmp_path):
    parsed = patterns.load(
        shared.write(tmp_path, shared.MERGE_ASK, {**shared.MERGE_ASK, "extra": "x"})
    )

    assert parsed.problems[0] == "merge-ask: 2 patterns share this id"


def test_a_file_that_isnt_toml_is_one_problem(tmp_path):
    parsed = patterns.parse("[[pattern]\n", tmp_path)

    assert parsed.patterns == []
    assert parsed.problems[0].startswith("not valid TOML")


def test_a_missing_file_is_one_problem(tmp_path):
    assert patterns.load(tmp_path / "nowhere.toml").problems[0].startswith("cannot read")


def test_a_relative_pattern_file_resolves_its_rule_file_from_its_own_directory(
    tmp_path, monkeypatch
):
    shared.write(tmp_path / "rules", shared.MERGE_ASK)
    monkeypatch.chdir(tmp_path)

    [found] = patterns.load(Path("rules/patterns.toml")).patterns

    assert found.rule_file == tmp_path / "rules" / "rules.md"
