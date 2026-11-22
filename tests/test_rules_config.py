from pathlib import Path

from lemonaid import rules_config


def test_the_check_is_off_until_a_pattern_file_is_named():
    assert rules_config.parse({}) == rules_config.RulesConfig(None, "")


def test_the_pattern_file_is_expanded():
    parsed = rules_config.parse({"patterns": "~/notes/patterns.toml", "report_to": " desk "})

    assert parsed == rules_config.RulesConfig(Path.home() / "notes" / "patterns.toml", "desk")


def test_a_value_of_the_wrong_type_warns_and_is_ignored(capsys):
    assert rules_config.parse({"patterns": 3}) == rules_config.RulesConfig()
    assert "[rules] patterns must be a string" in capsys.readouterr().err
